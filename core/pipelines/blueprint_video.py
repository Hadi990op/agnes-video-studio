"""core.pipelines.blueprint_video — Blueprint video pipeline.

The user provides a complete storyboard (scenes, prompts, character
descriptions, narration text) as a JSON file. The pipeline skips ALL
LLM generation steps and uses the blueprint data directly — generating
exactly what the user specified.

This allows recreating a specific movie style (e.g. "Kung Fu Panda") by
providing all scene prompts and character descriptions upfront.

Steps:
    build_scenes (from blueprint) → reference_images (from blueprint) →
    generate_videos → audio (TTS from blueprint narration) →
    subtitle → BGM mix → composite
"""

import asyncio
import json
import logging
import os
from typing import Callable, List, Optional

from core.api.agnes_image import AgnesImageAPI
from core.api.agnes_video import AgnesVideoAPI
from core.audio.tts import EdgeTTSEngine, SilentTTSEngine
from core.audio.bgm import mix_bgm_with_narration
from core.compositor.concatenator import VideoConcatenator
from core.pipelines import MultiScenePipeline, PipelineShutdown
from models.task import (
    BlueprintVideoTask,
    BlueprintScene,
    SceneTask,
    StepStatus,
)

logger = logging.getLogger(__name__)


class BlueprintPipeline(MultiScenePipeline):
    """Blueprint video pipeline — user provides the full storyboard.

    Unlike CreativeVideoPipeline which uses the LLM to generate stories,
    scripts, and prompts, this pipeline takes all creative content directly
    from the user's blueprint JSON. The LLM is only used for nothing —
    the user IS the screenwriter.
    """

    def __init__(
        self,
        api_key: str,
        task_id: str,
        dir_name: Optional[str] = None,
        image_model: str = "agnes-image-2.1-flash",
        video_model: str = "agnes-video-v2.0",
        progress_callback: Optional[Callable] = None,
        shutdown_event: Optional[asyncio.Event] = None,
    ):
        super().__init__(api_key, task_id, dir_name, progress_callback, shutdown_event)
        self.image_generator = AgnesImageAPI(api_key=api_key, model=image_model)
        self.video_generator = AgnesVideoAPI(api_key=api_key, model=video_model)
        self.video_generator.shutdown_event = shutdown_event
        self._state: Optional[BlueprintVideoTask] = None

    @property
    def state(self) -> Optional[BlueprintVideoTask]:
        return self._state

    def _get_init_message(self) -> str:
        title = self._state.title if self._state else "Blueprint"
        scene_count = len(self._state.blueprint_scenes) if self._state else 0
        return f"Blueprint: {title} ({scene_count} scenes)"

    # ==================================================================
    # Step 1: Build scenes from blueprint (NO LLM)
    # ==================================================================

    async def _build_scenes(self) -> None:
        """Convert blueprint scenes into SceneTask objects.

        No LLM involved — just maps the user's blueprint data to SceneTask.
        """
        bp_scenes = self._state.blueprint_scenes
        if not bp_scenes:
            raise PipelineShutdown("Blueprint has no scenes")

        await self._emit(
            "build_scenes", "running",
            f"Loading {len(bp_scenes)} scenes from blueprint...", 0.02,
        )

        scenes = []
        for bp in bp_scenes:
            scene = SceneTask(
                index=bp.index,
                scene_prompt=bp.video_prompt,
                narration_text=bp.narration,
                duration=bp.duration if bp.duration >= 2 else 5,
            )
            scenes.append(scene)

        self._state.scenes = scenes
        self.task_manager.update_state(
            scenes=[s.model_dump() for s in scenes],
            step_build_scenes=StepStatus.COMPLETED,
        )
        await self._emit(
            "build_scenes", "completed",
            f"Loaded {len(scenes)} scenes from blueprint", 0.05,
            {"scene_count": len(scenes)},
        )

    # ==================================================================
    # Step 2: Reference images (from blueprint character descriptions)
    # ==================================================================

    async def _build_reference_images(self) -> None:
        """Generate or use character reference images from blueprint.

        If the user uploaded a reference image, use it directly.
        If characters have descriptions, generate a reference image from
        the first character's description. Otherwise skip.
        """
        if self._state.step_reference_images == StepStatus.COMPLETED:
            if self._state.character_ref_file and os.path.exists(self._state.character_ref_file):
                logger.info("[Blueprint] Step reference_images: SKIP (already completed)")
                return

        await self._emit("reference_images", "running", "Preparing character reference...", 0.06)

        # If user uploaded a reference image, use it
        if self._state.reference_image and os.path.exists(self._state.reference_image):
            self._state.character_ref_file = self._state.reference_image
            self._state.step_reference_images = StepStatus.COMPLETED
            self.task_manager.update_state(
                character_ref_file=self._state.reference_image,
                step_reference_images=StepStatus.COMPLETED,
            )
            await self._emit("reference_images", "completed", "Using uploaded reference image", 0.10)
            return

        # If characters have descriptions, generate a reference image
        characters = self._state.characters
        if characters and characters[0].description:
            char_desc = characters[0].description
            style = self._state.style or ""
            full_prompt = f"{char_desc}, {style}" if style else char_desc

            ref_img_path = os.path.join(self.working_dir, "character_reference.png")
            if os.path.exists(ref_img_path):
                self._state.character_ref_file = ref_img_path
                self._state.step_reference_images = StepStatus.COMPLETED
                self.task_manager.update_state(
                    character_ref_file=ref_img_path,
                    step_reference_images=StepStatus.COMPLETED,
                )
                await self._emit("reference_images", "completed", "Character reference cached", 0.10)
                return

            await self._emit("reference_images", "running", "Generating character reference image...", 0.08)
            try:
                img_output = await self.image_generator.generate_single_image(
                    prompt=full_prompt,
                    size=f"{self._state.video_width}x{self._state.video_height}",
                )
                img_output.save(ref_img_path)
                self._state.character_ref_file = ref_img_path
            except Exception as e:
                logger.warning(f"[Blueprint] Character ref generation failed: {e}")
                # Continue without reference — videos will use text-only prompts

        self._state.step_reference_images = StepStatus.COMPLETED
        self.task_manager.update_state(
            character_ref_file=self._state.character_ref_file,
            step_reference_images=StepStatus.COMPLETED,
        )
        await self._emit("reference_images", "completed", "Reference images ready", 0.10)

    # ==================================================================
    # Step 3: Generate videos (from blueprint prompts)
    # ==================================================================

    async def _generate_videos(self) -> None:
        """Generate video for each scene using the blueprint's video_prompt.

        Uses t2v mode (text-to-video) since the user provided explicit prompts.
        If a character reference image exists, uses i2v (image-to-video) for
        better character consistency.
        """
        if self._state.step_video_generation == StepStatus.COMPLETED:
            if all(s.video_status == StepStatus.COMPLETED for s in self._state.scenes):
                logger.info("[Blueprint] Step video_generation: SKIP (all completed)")
                return

        total = len(self._state.scenes)
        ref_image = self._state.character_ref_file or ""
        has_ref = bool(ref_image and os.path.exists(ref_image))

        await self._emit(
            "video_generation", "running",
            f"Generating {total} videos ({'i2v' if has_ref else 't2v'})...", 0.11,
        )

        for i, scene in enumerate(self._state.scenes):
            self._check_shutdown()
            if scene.video_status == StepStatus.COMPLETED and scene.video_file and os.path.exists(scene.video_file):
                logger.info(f"[Blueprint] Scene {i}: SKIP (already completed)")
                continue

            progress = 0.10 + (i / total) * 0.55
            await self._emit(
                "video_generation", "running",
                f"Generating video {i+1}/{total}: {scene.scene_prompt[:60]}...",
                progress,
            )

            scene_dir = os.path.join(self.working_dir, f"scene_{i}")
            os.makedirs(scene_dir, exist_ok=True)
            video_path = os.path.join(scene_dir, "video.mp4")

            try:
                if has_ref:
                    # i2v: use reference image + scene prompt
                    result = await self.video_generator.generate_single_video(
                        prompt=scene.scene_prompt,
                        reference_image_paths=[ref_image],
                        duration=scene.duration,
                        width=self._state.video_width,
                        height=self._state.video_height,
                    )
                else:
                    # t2v: text only
                    result = await self.video_generator.generate_single_video(
                        prompt=scene.scene_prompt,
                        duration=scene.duration,
                        width=self._state.video_width,
                        height=self._state.video_height,
                    )

                # Save the video
                result.save(video_path)

                scene.video_file = video_path
                scene.video_status = StepStatus.COMPLETED
                scene.status = StepStatus.COMPLETED
                self.task_manager.update_state(
                    scenes=[s.model_dump() for s in self._state.scenes],
                )
                logger.info(f"[Blueprint] Scene {i} video completed: {video_path}")

            except Exception as e:
                logger.error(f"[Blueprint] Scene {i} video failed: {e}")
                scene.video_status = StepStatus.FAILED
                self.task_manager.update_state(
                    scenes=[s.model_dump() for s in self._state.scenes],
                )
                raise

        self._state.step_video_generation = StepStatus.COMPLETED
        self.task_manager.update_state(step_video_generation=StepStatus.COMPLETED)
        await self._emit("video_generation", "completed", f"All {total} videos generated", 0.65)

    # ==================================================================
    # Step 4: Audio (TTS from blueprint narration)
    # ==================================================================

    async def _generate_audio(self) -> Optional[object]:
        """Generate TTS narration from blueprint narration text.

        Concatenates all scene narration texts and generates a single
        TTS audio. If BGM is enabled, mixes it under the narration.
        """
        if self._state.step_audio == StepStatus.COMPLETED:
            if self._state.combined_audio and os.path.exists(self._state.combined_audio):
                logger.info("[Blueprint] Step audio: SKIP (already completed)")
                return None

        audio_enabled = self._state.audio_config.enabled
        narration_parts = [s.narration_text for s in self._state.scenes if s.narration_text]
        full_narration = "\n\n".join(narration_parts)
        total_duration = sum(float(s.duration) for s in self._state.scenes)

        await self._emit(
            "audio", "running",
            "Generating narration audio..." if audio_enabled else "Generating silent audio...",
            0.67,
        )

        combined_audio = os.path.join(self.working_dir, "combined_narration.mp3")
        sub_maker = None

        if audio_enabled and full_narration:
            edge_tts = EdgeTTSEngine()
            try:
                _, sub_maker = await edge_tts.generate(
                    text=full_narration,
                    output_path=combined_audio,
                    voice=self._state.audio_config.voice,
                    rate=self._state.audio_config.rate,
                )
            except RuntimeError as e:
                logger.warning(f"[Blueprint] EdgeTTS failed, falling back to silent: {e}")
                silent_tts = SilentTTSEngine()
                await silent_tts.generate(
                    text=full_narration,
                    output_path=combined_audio,
                    duration_sec=total_duration,
                )
        else:
            silent_tts = SilentTTSEngine()
            await silent_tts.generate(
                text=full_narration or "placeholder",
                output_path=combined_audio,
                duration_sec=total_duration,
            )

        # Mix BGM if enabled
        bgm_cfg = self._state.bgm_config
        if bgm_cfg.enabled and bgm_cfg.track != "none":
            await self._emit("audio", "running", "Mixing background music...", 0.70)
            mixed_audio = os.path.join(self.working_dir, "mixed_audio.mp3")
            result_path = mix_bgm_with_narration(
                narration_path=combined_audio,
                bgm_track_id=bgm_cfg.track,
                output_path=mixed_audio,
                bgm_volume=bgm_cfg.volume,
            )
            if result_path == mixed_audio:
                combined_audio = mixed_audio

        self._state.combined_audio = combined_audio
        self._state.step_audio = StepStatus.COMPLETED
        self.task_manager.update_state(
            combined_audio=combined_audio,
            step_audio=StepStatus.COMPLETED,
        )
        await self._emit("audio", "completed", "Audio generation complete", 0.75)
        return sub_maker

    # ==================================================================
    # Step 5: Subtitle
    # ==================================================================

    async def _generate_subtitles(self, sub_maker: Optional[object] = None) -> None:
        """Generate SRT subtitles from blueprint narration text."""
        if self._state.step_subtitle == StepStatus.COMPLETED:
            logger.info("[Blueprint] Step subtitle: SKIP (already completed)")
            return

        if not self._state.subtitle_config.enabled:
            self._state.step_subtitle = StepStatus.COMPLETED
            self.task_manager.update_state(step_subtitle=StepStatus.COMPLETED)
            return

        await self._emit("subtitle", "running", "Generating subtitles...", 0.76)

        segment_texts = [s.narration_text for s in self._state.scenes]
        segment_durations = [float(s.duration) for s in self._state.scenes]

        srt_path, _ = await self.generate_subtitles_common(
            segment_texts=segment_texts,
            segment_durations=segment_durations,
            subtitle_config=self._state.subtitle_config,
            sub_maker=sub_maker,
            audio_path=self._state.combined_audio,
            srt_filename="combined_narration.srt",
            screenwriter=None,  # No LLM in blueprint mode
            video_width=self._state.video_width,
            video_height=self._state.video_height,
        )

        self._state.combined_subtitle = srt_path
        self._state.step_subtitle = StepStatus.COMPLETED
        self.task_manager.update_state(
            combined_subtitle=srt_path,
            step_subtitle=StepStatus.COMPLETED,
        )
        await self._emit("subtitle", "completed", "Subtitles generated", 0.80)

    # ==================================================================
    # Step 6: Composite final video
    # ==================================================================

    async def _composite_final(self) -> str:
        """Concatenate all scene videos with audio overlay + subtitles."""
        if self._state.step_concatenation == StepStatus.COMPLETED:
            if self._state.final_video_file and os.path.exists(self._state.final_video_file):
                logger.info("[Blueprint] Step concatenation: SKIP (already completed)")
                return self._state.final_video_file

        await self._emit("concatenation", "running", "Concatenating videos...", 0.82)

        video_paths = [
            s.video_file for s in self._state.scenes
            if s.video_file and os.path.exists(s.video_file)
        ]
        if not video_paths:
            raise PipelineShutdown("No scene videos found to concatenate")

        output_path = os.path.join(self.working_dir, "final_video.mp4")
        audio_path = self._state.combined_audio if self._state.audio_config.enabled else ""
        srt_path = self._state.combined_subtitle if self._state.subtitle_config.enabled else ""

        # Use the concatenator with audio overlay + subtitles
        VideoConcatenator.concat_videos_with_audio_overlay(
            video_paths=video_paths,
            audio_path=audio_path,
            output_path=output_path,
            srt_path=srt_path if srt_path else None,
            subtitle_style=self._state.subtitle_config.style if self._state.subtitle_config.enabled else None,
        )

        # Apply watermark
        output_path = self._apply_watermark(output_path)

        self._state.final_video_file = output_path
        self._state.step_concatenation = StepStatus.COMPLETED
        self._state.status = StepStatus.COMPLETED
        self.task_manager.update_state(
            final_video_file=output_path,
            step_concatenation=StepStatus.COMPLETED,
            status=StepStatus.COMPLETED,
        )
        await self._emit("concatenation", "completed", "Video complete!", 1.0)
        return output_path

    # ==================================================================
    # Hook methods for MultiScenePipeline
    # ==================================================================

    def _get_narration_text(self) -> str:
        return "\n\n".join(s.narration_text for s in self._state.scenes if s.narration_text)

    def _get_segment_texts_and_durations(self):
        texts = [s.narration_text for s in self._state.scenes]
        durations = [float(s.duration) for s in self._state.scenes]
        return texts, durations

    def _get_scene_video_prompt(self, scene: SceneTask) -> str:
        return scene.scene_prompt

    def _get_scene_ref_images(self, scene: SceneTask) -> list:
        if self._state.character_ref_file and os.path.exists(self._state.character_ref_file):
            return [self._state.character_ref_file]
        return []

    def _get_scene_duration(self, scene: SceneTask) -> int:
        return scene.duration

    def _get_audio_path(self) -> str:
        return self._state.combined_audio

    def _set_subtitle_paths(self, srt_path: str, styles_path: str = "") -> None:
        self._state.combined_subtitle = srt_path

    def _get_watermark_language_text(self) -> str:
        return self._state.title or (self._state.scenes[0].narration_text if self._state.scenes else "")
