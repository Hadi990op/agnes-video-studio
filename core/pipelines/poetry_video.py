"""core.pipelines.poetry_video -- 诗词视频流水线（类型 6 / v4.0 Phase 5）

用户提供诗词文本 → 按段落（空行）拆分为场景 → LLM 生成诗意化视频 prompt →
逐段生成视频 → TTS 朗诵配音 + 字幕叠加 → 拼接为最终诗词视频。

v4.0 重构：继承 MultiScenePipeline，复用模板方法 run() 与步骤编排。
_logic 接近 Manuscript，差异仅在文本拆分与 prompt 生成策略。
"""

import asyncio
import json
import logging
import os
import re
from typing import Callable, Optional

from core.api.agnes_video import AgnesVideoAPI
from core.audio.tts import EdgeTTSEngine, SilentTTSEngine
from core.compositor.concatenator import VideoConcatenator
from core.pipelines import MultiScenePipeline
from core.screenwriter import Screenwriter
from models.task import (
    PoetryVideoTask,
    SceneTask,
    StepStatus,
    AudioConfig,
    SubtitleConfig,
)

logger = logging.getLogger(__name__)

_STANZA_RE = re.compile(r"\n\s*\n")
_CHARS_PER_SEC = 4.0


class PoetryVideoPipeline(MultiScenePipeline):
    """诗词视频生成流水线。

    诗词文本 → 拆分诗节 → LLM 场景 prompt → 视频生成 → 朗诵配音+字幕 → 合成。
    """

    def __init__(
        self,
        api_key: str,
        task_id: str,
        dir_name: Optional[str] = None,
        chat_model: str = "agnes-2.0-flash",
        video_model: str = "agnes-video-v2.0",
        progress_callback: Optional[Callable] = None,
        shutdown_event: Optional = None,
    ):
        super().__init__(api_key, task_id, dir_name, progress_callback, shutdown_event)
        self.screenwriter = Screenwriter(api_key=api_key, model=chat_model)
        self._state: Optional[PoetryVideoTask] = None

    @property
    def state(self) -> Optional[PoetryVideoTask]:
        return self._state

    # ------------------------------------------------------------------
    # 水印语言
    # ------------------------------------------------------------------

    def _get_watermark_language_text(self) -> str:
        return self._state.poem_text

    # ------------------------------------------------------------------
    # 数据来源：分镜（拆分诗节 → LLM 场景 prompt）
    # ------------------------------------------------------------------

    async def _build_scenes(self) -> None:
        """拆诗节 + 生成每个场景的 LLM prompt。"""
        poem = self._state.poem_text.strip()
        if not poem:
            self._state.scenes = []
            return

        # 按空行拆诗节
        raw_stanzas = [s.strip() for s in _STANZA_RE.split(poem) if s.strip()]
        if not raw_stanzas:
            raw_stanzas = [poem]

        duration = max(int(self._state.video_duration), 3)
        scenes: list[SceneTask] = []

        for idx, stanza in enumerate(raw_stanzas):
            await self._emit(
                "build_scenes", "running",
                f"生成第 {idx + 1}/{len(raw_stanzas)} 段诗词视觉描述...",
                0.05 + 0.10 * idx / max(len(raw_stanzas), 1),
            )

            prompt = await self._get_prompt_for_stanza(stanza, poem, idx)
            scene = SceneTask(
                index=idx,
                scene_prompt=prompt,
                duration=duration,
                narration_text=stanza,
            )
            scenes.append(scene)

        self._state.scenes = scenes
        self.task_manager.update_state(
            scenes=[s.model_dump() for s in scenes],
        )

    async def _get_prompt_for_stanza(
        self, stanza: str, full_poem: str, idx: int
    ) -> str:
        """为单个诗节生成视频场景 prompt（LLM）。"""
        return await asyncio.to_thread(
            self.screenwriter.generate_poetry_scene_prompt,
            stanza,
            poem_context=full_poem,
        )

    # ------------------------------------------------------------------
    # 参考图：无（诗词视频不需参考图）
    # ------------------------------------------------------------------

    async def _build_reference_images(self) -> None:
        """诗词视频不需参考图，跳过此阶段。"""
        pass

    # ------------------------------------------------------------------
    # 视频生成（逐段，覆写通用实现以保留目录结构 resume）
    # ------------------------------------------------------------------

    async def _generate_videos(self) -> None:
        """逐段生成视频，每段存 scene_{idx}/video.mp4。"""
        scenes = self._state.scenes
        vw = self._state.video_width
        vh = self._state.video_height

        for idx, scene in enumerate(scenes):
            scene_dir = os.path.join(self.working_dir, f"scene_{idx}")
            os.makedirs(scene_dir, exist_ok=True)
            video_path = os.path.join(scene_dir, "video.mp4")

            if os.path.exists(video_path):
                scene.video_file = video_path
                logger.info(f"[Poetry] scene {idx}: video already exists, skipping")
                continue

            video_id = self._load_task_json(scene_dir)
            if not video_id:
                vg = AgnesVideoAPI(api_key=self.api_key, model="agnes-video-v2.0")
                video_id = await vg.submit_video(
                    prompt=scene.scene_prompt,
                    duration=int(scene.duration),
                    width=vw,
                    height=vh,
                )
                self._save_task_json(scene_dir, {"video_id": video_id})

            vg = AgnesVideoAPI(api_key=self.api_key, model="agnes-video-v2.0")
            for retry in range(3):
                try:
                    vo = await vg.wait_for_video(video_id)
                    vo.save(video_path)
                    break
                except Exception as e:
                    if retry < 2:
                        logger.warning(
                            f"[Poetry] scene {idx} retry {retry+1}: {e}"
                        )
                        await asyncio.sleep(15 * (retry + 1))
                    else:
                        raise
            scene.video_file = video_path

        self.task_manager.update_state(
            scenes=[s.model_dump() for s in scenes],
        )

    # ------------------------------------------------------------------
    # 音频生成（整段朗诵，覆写通用实现）
    # ------------------------------------------------------------------

    async def _generate_audio(self) -> Optional[object]:
        """生成整段朗诵音频（TTS）。"""

        full_text = self._state.poem_text.strip()
        if not full_text:
            return None

        audio_path = os.path.join(self.working_dir, "full_narration.mp3")
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            self._state.combined_audio = audio_path
            return None

        audio_config = self._state.audio_config
        edge_tts = EdgeTTSEngine()
        silent_tts = SilentTTSEngine()

        await self._emit("audio", "running", f"生成朗诵配音 ({len(full_text)} 字)...", 0.75)

        sub_maker = None
        if audio_config.enabled:
            try:
                _, sub_maker = await edge_tts.generate(
                    text=full_text,
                    output_path=audio_path,
                    voice=audio_config.voice,
                    rate=audio_config.rate,
                )
            except RuntimeError as e:
                logger.warning(f"[Poetry] EdgeTTS failed: {e}, using silent")
                duration = len(full_text) / _CHARS_PER_SEC
                await silent_tts.generate(
                    text=full_text, output_path=audio_path,
                    duration_sec=duration,
                )
        else:
            duration = len(full_text) / _CHARS_PER_SEC
            await silent_tts.generate(
                text=full_text, output_path=audio_path,
                duration_sec=duration,
            )

        self._state.combined_audio = audio_path
        self.task_manager.update_state(combined_audio=audio_path)
        return sub_maker

    # ------------------------------------------------------------------
    # 字幕生成（整段朗诵字幕，覆写通用实现）
    # ------------------------------------------------------------------

    async def _generate_subtitles(self, sub_maker: Optional[object] = None) -> None:
        """生成整段朗诵字幕。"""
        full_text = self._state.poem_text.strip()
        if not full_text:
            return

        subtitle_config = self._state.subtitle_config
        if not subtitle_config.enabled:
            return

        # 整段文本，单一 SRT
        segment_texts = [full_text]
        segment_durations = [max(len(full_text) / _CHARS_PER_SEC, 3.0)]

        await self._emit("subtitle", "running", f"生成朗诵字幕 ({len(full_text)} 字)...", 0.80)

        srt_path, styles_path = await self.generate_subtitles_common(
            segment_texts=segment_texts,
            segment_durations=segment_durations,
            subtitle_config=subtitle_config,
            sub_maker=sub_maker,
            audio_path=self._state.combined_audio or "",
            screenwriter=self.screenwriter,
            video_width=self._state.video_width,
            video_height=self._state.video_height,
            role="poetry recitation",
        )

        if styles_path:
            self._state.subtitle_styles_path = styles_path
            self.task_manager.update_state(subtitle_styles_path=styles_path)

        self._state.combined_subtitle = srt_path
        self.task_manager.update_state(combined_subtitle=srt_path)

    # ------------------------------------------------------------------
    # 合成（拼接 + 音频叠加）
    # ------------------------------------------------------------------

    async def _composite_final(self) -> str:
        """拼接所有场景视频 + 叠加朗诵音频和字幕。"""

        output_path = os.path.join(self.working_dir, "final_video.mp4")
        if os.path.exists(output_path):
            logger.info("[Poetry] composite: final video already exists, skipping")
            return output_path

        all_paths = [s.video_file for s in self._state.scenes if s.video_file]
        if not all_paths:
            raise RuntimeError("[Poetry] No videos to composite")

        combined_audio = self._state.combined_audio or ""
        combined_srt = self._state.combined_subtitle or ""
        has_audio = self._state.audio_config.enabled
        has_subtitle = self._state.subtitle_config.enabled
        styles_path = self._state.subtitle_styles_path or ""

        await self._emit("concatenate", "running", "拼接诗词视频...", 0.90)

        audio_exists = os.path.exists(combined_audio) and os.path.getsize(combined_audio) > 0
        srt_exists = os.path.exists(combined_srt) and os.path.getsize(combined_srt) > 0

        if audio_exists and has_audio:
            await asyncio.to_thread(
                VideoConcatenator.concat_videos_with_audio_overlay,
                video_paths=all_paths,
                audio_path=combined_audio,
                srt_path=combined_srt if (has_subtitle and srt_exists) else None,
                output_path=output_path,
                subtitle_style=self._state.subtitle_config.style if has_subtitle else None,
                subtitle_styles_path=styles_path if styles_path else None,
            )
        else:
            await asyncio.to_thread(
                VideoConcatenator.concat_videos, all_paths, output_path
            )

        return output_path
