"""core.pipelines.poetry_video -- 诗词视频流水线（类型 6 / v4.0）

用户输入古诗 → LLM 拆分为若干场景（narration=原诗句, scene_prompt=视频描述）
→ 逐场景 t2v 生成 → 逐场景 TTS 朗诵配音 + 该句字幕（定时对齐）→ 逐场景合成后拼接。

与创意视频的区别：创意从 idea 经 story/script 生成 narration+prompt；
诗歌直接由 LLM 从原诗拆分出 narration(原诗句) + scene_prompt(视频描述)。
字幕/配音定制：逐场景生成，每句间隔由场景视频时长补足（拉长间隔，诗句↔画面一一对应）。
"""

import asyncio
import logging
import os
import shutil
from typing import List, Optional

from core.api.agnes_video import AgnesVideoAPI
from core.audio.subtitle import SubtitleGenerator
from core.audio.tts import EdgeTTSEngine, SilentTTSEngine
from core.compositor.concatenator import VideoConcatenator
from core.pipelines import MultiScenePipeline
from core.screenwriter import Screenwriter
from models.task import (
    PoetryVideoTask,
    SceneTask,
    StepStatus,
    SubtitleStyle,
)

logger = logging.getLogger(__name__)

# 诗歌固定字幕样式：居中偏下、白字黑描边、半透明底（用户只开关，不选样式）
POETRY_SUBTITLE_STYLE = SubtitleStyle(
    font="STHeitiMedium.ttc",
    color="white",
    position=("center", "bottom-80"),
    fontsize=48,
    stroke_color="black",
    stroke_width=2,
    bg_color=(0, 0, 0, 140),
)

_CHARS_PER_SEC = 4.0


class PoetryVideoPipeline(MultiScenePipeline):
    """诗词视频生成流水线。

    古诗原文 → LLM 拆分场景(narration+scene_prompt) → 逐场景视频生成 →
    逐场景朗诵配音 + 该句字幕 → 逐场景合成后拼接。
    """

    def __init__(
        self,
        api_key: str,
        task_id: str,
        dir_name: Optional[str] = None,
        chat_model: str = "agnes-2.0-flash",
        video_model: str = "agnes-video-v2.0",
        progress_callback: Optional[callable] = None,
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
    # Phase 1: 分镜（LLM 拆分原诗 → scenes）
    # ------------------------------------------------------------------

    async def _build_scenes(self) -> None:
        """LLM 拆分整首诗词为若干场景，保留原诗句作为 narration。"""
        poem = self._state.poem_text.strip()
        if not poem:
            self._state.scenes = []
            return

        raw_scenes = await asyncio.to_thread(
            self.screenwriter.generate_poetry_scenes,
            poem,
            self._state.video_duration,
            self._state.scene_count,
            self._state.style,
        )
        if not raw_scenes:
            raise RuntimeError("[Poetry] LLM 未返回有效场景，请重试")

        # 用户可选分镜 prompt：按索引覆盖 scene_prompt（优雅降级）
        user_prompts = self._state.user_scene_prompts or []

        # 时长均分（诗歌较短，每景给足时长以拉长句间间隔）
        total = max(int(self._state.video_duration), len(raw_scenes) * 3)
        per = max(int(total / len(raw_scenes)), 3)

        scenes: List[SceneTask] = []
        for idx, sc in enumerate(raw_scenes):
            narration = (sc.get("narration") or "").strip()
            prompt = (sc.get("scene_prompt") or "").strip()
            # 用户提供了该索引的分镜 prompt → 覆盖 LLM 生成
            if idx < len(user_prompts) and user_prompts[idx].strip():
                prompt = user_prompts[idx].strip()
            scenes.append(SceneTask(
                index=idx,
                scene_prompt=prompt,
                narration_text=narration,
                duration=per,
            ))

        self._state.scenes = scenes
        self.task_manager.update_state(scenes=[s.model_dump() for s in scenes])
        # 记录 LLM 生成的 prompt 供 verify_prompts 校验
        self.save_prompts({
            "poem_text": poem,
            "scene_prompts": [s.scene_prompt for s in scenes],
            "narrations": [s.narration_text for s in scenes],
        })

    async def _build_reference_images(self) -> None:
        """诗词视频不需参考图，跳过。"""
        pass

    # ------------------------------------------------------------------
    # Phase 3: 视频生成（逐场景 t2v）
    # ------------------------------------------------------------------

    async def _generate_videos(self) -> None:
        """逐场景生成视频，每段存 scene_{idx}/video.mp4。"""
        scenes = self._state.scenes
        vw = self._state.video_width
        vh = self._state.video_height

        for idx, scene in enumerate(scenes):
            scene_dir = os.path.join(self.working_dir, f"scene_{idx}")
            os.makedirs(scene_dir, exist_ok=True)
            video_path = os.path.join(scene_dir, "video.mp4")

            if os.path.exists(video_path):
                scene.video_file = video_path
                logger.info(f"[Poetry] scene {idx}: video exists, skip")
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
    # Phase 4: 配音（逐场景 TTS narration_text）
    # ------------------------------------------------------------------

    async def _generate_audio(self) -> Optional[object]:
        """逐场景生成朗诵配音，每段存 scene_{idx}/narration.mp3。

        返回 None（字幕由各场景独立生成，不使用全局 sub_maker）。
        """
        scenes = self._state.scenes
        audio_config = self._state.audio_config
        has_audio = audio_config.enabled

        for idx, scene in enumerate(scenes):
            scene_dir = os.path.join(self.working_dir, f"scene_{idx}")
            os.makedirs(scene_dir, exist_ok=True)
            audio_path = os.path.join(scene_dir, "narration.mp3")

            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                scene.narration_audio = audio_path
                continue

            text = (scene.narration_text or "").strip()
            if not text:
                # 无朗诵文本：生成静音占位（时长=场景时长），保证合成链路统一
                silent = SilentTTSEngine()
                await silent.generate(
                    text=" ", output_path=audio_path,
                    duration_sec=max(int(scene.duration), 2),
                )
                scene.narration_audio = audio_path
                continue

            await self._emit(
                "audio", "running",
                f"生成朗诵配音 {idx+1}/{len(scenes)}...", 0.75,
            )
            edge_tts = EdgeTTSEngine()
            silent = SilentTTSEngine()
            try:
                if has_audio:
                    await edge_tts.generate(
                        text=text, output_path=audio_path,
                        voice=audio_config.voice, rate=audio_config.rate,
                    )
                else:
                    # 关闭配音：仍生成静音占位，保证合成链路统一
                    await silent.generate(
                        text=text, output_path=audio_path,
                        duration_sec=max(int(scene.duration), 2),
                    )
            except RuntimeError as e:
                logger.warning(f"[Poetry] scene {idx} TTS failed: {e}, silent")
                await silent.generate(
                    text=text, output_path=audio_path,
                    duration_sec=max(int(scene.duration), 2),
                )
            scene.narration_audio = audio_path

        self.task_manager.update_state(
            scenes=[s.model_dump() for s in scenes],
        )
        return None

    # ------------------------------------------------------------------
    # Phase 5: 字幕（逐场景 SRT，定时对齐朗诵）
    # ------------------------------------------------------------------

    async def _generate_subtitles(self, sub_maker: Optional[object] = None) -> None:
        """逐场景生成字幕，每段存 scene_{idx}/subtitle.srt。

        字幕只在朗诵时段显示，其余为静默画面（句间间隔拉长）。
        """
        scenes = self._state.scenes
        sub_config = self._state.subtitle_config
        if not sub_config.enabled:
            return

        for idx, scene in enumerate(scenes):
            scene_dir = os.path.join(self.working_dir, f"scene_{idx}")
            os.makedirs(scene_dir, exist_ok=True)
            srt_path = os.path.join(scene_dir, "subtitle.srt")

            if os.path.exists(srt_path) and os.path.getsize(srt_path) > 0:
                scene.subtitle_srt = srt_path
                continue

            text = (scene.narration_text or "").strip()
            if not text:
                continue

            # 字幕时长 = 朗诵音频时长（首段显示，余下静默）
            audio_dur = self.get_audio_duration(scene.narration_audio or "")
            dur = max(audio_dur, 1.0)
            await self._emit(
                "subtitle", "running",
                f"生成字幕 {idx+1}/{len(scenes)}...", 0.87,
            )
            SubtitleGenerator.text_to_srt(
                text, srt_path, duration_sec=dur, chars_per_sec=_CHARS_PER_SEC,
            )
            scene.subtitle_srt = srt_path

        self.task_manager.update_state(
            scenes=[s.model_dump() for s in scenes],
        )

    # ------------------------------------------------------------------
    # Phase 6: 合成（逐场景 composite 后拼接）
    # ------------------------------------------------------------------

    async def _composite_final(self) -> str:
        """逐场景合成 video+audio+subtitle → final_clip，再拼接为成片。

        合成器自动将每场景音频补静音至视频时长，即"每句间隔拉长"的实现。
        """
        scenes = self._state.scenes
        has_subtitle = self._state.subtitle_config.enabled

        final_clips = []
        for idx, scene in enumerate(scenes):
            scene_dir = os.path.join(self.working_dir, f"scene_{idx}")
            video_path = scene.video_file
            if not video_path or not os.path.exists(video_path):
                raise RuntimeError(f"[Poetry] scene {idx} video missing")

            audio_path = scene.narration_audio or ""
            srt_path = scene.subtitle_srt or ""
            clip_out = os.path.join(scene_dir, "final_clip.mp4")

            if os.path.exists(clip_out) and os.path.getsize(clip_out) > 0:
                final_clips.append(clip_out)
                continue

            # 兜底：音频缺失则生成静音占位，保证合成不中断
            audio_exists = os.path.exists(audio_path) and os.path.getsize(audio_path) > 0
            if not audio_exists:
                audio_path = os.path.join(scene_dir, "narration.mp3")
                await SilentTTSEngine().generate(
                    text=" ", output_path=audio_path,
                    duration_sec=max(int(scene.duration), 2),
                )
                scene.narration_audio = audio_path
                audio_exists = True

            srt_exists = os.path.exists(srt_path) and os.path.getsize(srt_path) > 0

            await self._emit(
                "concatenate", "running",
                f"合成场景 {idx+1}/{len(scenes)}...", 0.90,
            )
            await asyncio.to_thread(
                VideoConcatenator.concat_videos_with_audio_overlay,
                [video_path],
                audio_path,
                srt_path if (has_subtitle and srt_exists) else None,
                clip_out,
                POETRY_SUBTITLE_STYLE,
                None,
            )
            final_clips.append(clip_out)

        output_path = os.path.join(self.working_dir, "final_video.mp4")
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path

        if len(final_clips) == 1:
            shutil.copy2(final_clips[0], output_path)
        else:
            await asyncio.to_thread(
                VideoConcatenator.concat_videos, final_clips, output_path,
            )
        return output_path
