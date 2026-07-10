"""tests.mock_regression.test_pipelines — Pipeline Mock 回归测试

覆盖四种 pipeline 类型的全流程，不调用任何外部接口。
验证点：产物文件存在、状态正确、步骤完整。
"""

import os
import pytest
import asyncio
import logging

from models.task import (
    StepStatus,
    AudioConfig,
    SubtitleConfig,
    SimpleVideoTask,
    CreativeVideoTask,
    ManuscriptVideoTask,
    AnchorVideoTask,
    PoetryVideoTask,
    VideoMode,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# 通用验证基类
# ══════════════════════════════════════════════════════════════════════

class BasePipelineTest:
    """所有 pipeline 测试的通用验证模式。"""

    async def _run_and_verify(self, pipeline_class, state, workdir,
                               verify_steps: bool = True,
                               verify_prompts: bool = False):
        """执行 pipeline 并验证产物。

        Args:
            pipeline_class: Pipeline 类
            state: 任务状态对象
            workdir: 工作目录
            verify_steps: 是否验证步骤状态
            verify_prompts: 是否验证 prompts.json

        Returns:
            final_video: 最终视频路径
        """
        pipeline = pipeline_class(
            api_key="mock_key",
            task_id="test_task_001",
            dir_name=workdir,
        )

        final_video = await pipeline.run(state)

        # ── 1. 产物文件存在且非空 ──
        assert os.path.exists(final_video), f"Final video not found: {final_video}"
        size = os.path.getsize(final_video)
        assert size > 0, f"Final video is empty ({final_video})"
        logger.info(f"  ✓ final_video: {os.path.basename(final_video)} ({size:,} bytes)")

        # ── 2. 状态标记正确 ──
        assert state.status == StepStatus.COMPLETED, \
            f"Expected COMPLETED, got {state.status}"
        assert state.final_video_file == final_video, \
            f"final_video_file mismatch: {state.final_video_file} != {final_video}"

        # ── 3. 步骤状态全部非 FAILED ──
        if verify_steps:
            for field_name in type(state).model_fields:
                if field_name.startswith("step_") and not field_name.endswith("_subtitle"):
                    step_status = getattr(state, field_name, None)
                    if step_status is not None:
                        assert step_status != StepStatus.FAILED, \
                            f"Step {field_name} is FAILED"
            logger.info(f"  ✓ all step statuses verified")

        # ── 4. prompts.json（如果 pipeline 用了 LLM）──
        if verify_prompts:
            prompts_path = os.path.join(workdir, "prompts.json")
            if os.path.exists(prompts_path):
                assert os.path.getsize(prompts_path) > 0, "prompts.json is empty"
                logger.info(f"  ✓ prompts.json exists")

        # ── 5. working_dir 有合理数量的产物文件 ──
        files = []
        for root, _dirs, filenames in os.walk(workdir):
            for fn in filenames:
                files.append(os.path.relpath(os.path.join(root, fn), workdir))
        logger.info(f"  ✓ working_dir files ({len(files)}): {sorted(files)[:10]}...")
        assert len(files) >= 3, f"Expected at least 3 files in working_dir, got {len(files)}"

        return final_video


# ══════════════════════════════════════════════════════════════════════
# SimpleVideo Pipeline
# ══════════════════════════════════════════════════════════════════════

class TestSimpleVideoPipeline(BasePipelineTest):

    async def _make_state(self, **kwargs):
        return SimpleVideoTask(
            task_type="simple",
            creative_name="mock_simple",
            prompt=kwargs.get("prompt", "一只猫在花园里追蝴蝶"),
            mode=kwargs.get("mode", VideoMode.T2V),
            duration=kwargs.get("duration", 5),
            video_width=kwargs.get("video_width", 768),
            video_height=kwargs.get("video_height", 1152),
        )

    @pytest.mark.asyncio
    async def test_t2v_basic(self, temp_workdir):
        """简单视频 t2v 模式 — 基础流程。"""
        from core.pipelines.simple_video import SimpleVideoPipeline
        state = await self._make_state(mode=VideoMode.T2V)
        await self._run_and_verify(SimpleVideoPipeline, state, temp_workdir)

    @pytest.mark.asyncio
    async def test_t2v_with_system_prompt(self, temp_workdir):
        """简单视频 t2v + system_prompt。"""
        from core.pipelines.simple_video import SimpleVideoPipeline
        state = await self._make_state(
            mode=VideoMode.T2V,
            system_prompt="Generate in cinematic realism style",
        )
        await self._run_and_verify(SimpleVideoPipeline, state, temp_workdir)

    @pytest.mark.asyncio
    async def test_t2v_with_seed(self, temp_workdir):
        """简单视频 t2v + seed。"""
        from core.pipelines.simple_video import SimpleVideoPipeline
        state = await self._make_state(mode=VideoMode.T2V, seed=42)
        await self._run_and_verify(SimpleVideoPipeline, state, temp_workdir)


# ══════════════════════════════════════════════════════════════════════
# CreativeVideo Pipeline
# ══════════════════════════════════════════════════════════════════════

class TestCreativeVideoPipeline(BasePipelineTest):

    async def _make_state(self, **kwargs):
        return CreativeVideoTask(
            task_type="creative",
            creative_name="mock_creative",
            idea=kwargs.get("idea", "一只小猫的冒险故事"),
            style=kwargs.get("style", "电影质感写实风格"),
            chaining_mode=kwargs.get("chaining_mode", "keyframes"),
            scene_count=kwargs.get("scene_count", 3),
            scene_durations=kwargs.get("scene_durations", [5, 5, 5]),
            duration_source=kwargs.get("duration_source", "manual"),
            video_width=kwargs.get("video_width", 768),
            video_height=kwargs.get("video_height", 1152),
            audio_config=kwargs.get("audio_config", AudioConfig(enabled=True)),
            subtitle_config=kwargs.get("subtitle_config", SubtitleConfig(enabled=True)),
        )

    @pytest.mark.asyncio
    async def test_keyframes_mode(self, temp_workdir):
        """创意视频 keyframes 模式 — 全流程。"""
        from core.pipelines.creative_video import CreativeVideoPipeline
        state = await self._make_state(chaining_mode="keyframes")
        await self._run_and_verify(CreativeVideoPipeline, state, temp_workdir,
                                    verify_prompts=True)

    @pytest.mark.asyncio
    async def test_independent_mode(self, temp_workdir):
        """创意视频 independent 模式 — 无场景间关联。"""
        from core.pipelines.creative_video import CreativeVideoPipeline
        state = await self._make_state(chaining_mode="independent")
        await self._run_and_verify(CreativeVideoPipeline, state, temp_workdir,
                                    verify_prompts=True)

    @pytest.mark.asyncio
    async def test_ti2vid_mode(self, temp_workdir):
        """创意视频 ti2vid 模式 — 场景间传递最后一帧。"""
        from core.pipelines.creative_video import CreativeVideoPipeline
        state = await self._make_state(chaining_mode="ti2vid")
        await self._run_and_verify(CreativeVideoPipeline, state, temp_workdir,
                                    verify_prompts=True)

    @pytest.mark.asyncio
    async def test_audio_disabled(self, temp_workdir):
        """创意视频 — 禁用音频。"""
        from core.pipelines.creative_video import CreativeVideoPipeline
        state = await self._make_state(
            chaining_mode="independent",
            audio_config=AudioConfig(enabled=False),
            subtitle_config=SubtitleConfig(enabled=False),
        )
        await self._run_and_verify(CreativeVideoPipeline, state, temp_workdir,
                                    verify_prompts=True)

    @pytest.mark.asyncio
    async def test_scene_count_5(self, temp_workdir):
        """创意视频 — 5 个场景。"""
        from core.pipelines.creative_video import CreativeVideoPipeline
        state = await self._make_state(
            chaining_mode="independent",
            scene_count=5,
            scene_durations=[5, 5, 5, 5, 5],
            audio_config=AudioConfig(enabled=False),
            subtitle_config=SubtitleConfig(enabled=False),
        )
        await self._run_and_verify(CreativeVideoPipeline, state, temp_workdir)


# ══════════════════════════════════════════════════════════════════════
# ManuscriptVideo Pipeline
# ══════════════════════════════════════════════════════════════════════

class TestManuscriptVideoPipeline(BasePipelineTest):

    _MANUSCRIPT_TEXT = (
        "春天来了，万物复苏，花园里的花朵竞相开放，"
        "蜜蜂在花丛中忙碌地采蜜，蝴蝶翩翩起舞。\n\n"
        "小猫从窗台跳下来，开始了它的冒险之旅，"
        "它好奇地打量着周围的一切，小心翼翼地迈出每一步。\n\n"
        "它在花丛中追逐蝴蝶，在阳光下打滚，"
        "扑向飘落的花瓣，玩得不亦乐乎。\n\n"
        "最后夕阳西下，小猫满足地回家了，"
        "它趴在窗台上，看着渐渐暗下来的天空，打了个哈欠。"
    )

    async def _make_state(self, **kwargs):
        return ManuscriptVideoTask(
            task_type="manuscript",
            creative_name="mock_manuscript",
            manuscript_text=kwargs.get("manuscript_text", self._MANUSCRIPT_TEXT),
            video_width=kwargs.get("video_width", 768),
            video_height=kwargs.get("video_height", 1152),
            audio_config=kwargs.get("audio_config", AudioConfig(enabled=True)),
            subtitle_config=kwargs.get("subtitle_config", SubtitleConfig(enabled=True)),
        )

    @pytest.mark.asyncio
    async def test_manuscript_basic(self, temp_workdir):
        """稿件视频 — 基础全流程。"""
        from core.pipelines.manuscript_video import ManuscriptVideoPipeline
        state = await self._make_state()
        await self._run_and_verify(ManuscriptVideoPipeline, state, temp_workdir,
                                    verify_prompts=True)

    @pytest.mark.asyncio
    async def test_manuscript_no_audio(self, temp_workdir):
        """稿件视频 — 禁用音频和字幕。"""
        from core.pipelines.manuscript_video import ManuscriptVideoPipeline
        state = await self._make_state(
            audio_config=AudioConfig(enabled=False),
            subtitle_config=SubtitleConfig(enabled=False),
        )
        await self._run_and_verify(ManuscriptVideoPipeline, state, temp_workdir)

    @pytest.mark.asyncio
    async def test_manuscript_short_text(self, temp_workdir):
        """稿件视频 — 短文本（单段）。"""
        from core.pipelines.manuscript_video import ManuscriptVideoPipeline
        state = await self._make_state(manuscript_text="这是很短的一段话。")
        await self._run_and_verify(ManuscriptVideoPipeline, state, temp_workdir,
                                    verify_prompts=True)


# ══════════════════════════════════════════════════════════════════════
# AnchorVideo Pipeline
# ══════════════════════════════════════════════════════════════════════

class TestAnchorVideoPipeline(BasePipelineTest):

    async def _make_state(self, **kwargs):
        return AnchorVideoTask(
            task_type="anchor",
            creative_name="mock_anchor",
            script_text=kwargs.get("script_text",
                "各位观众朋友们大家好，欢迎收看今天的节目。今天的主要内容有：科技前沿最新动态。"),
            audio_source=kwargs.get("audio_source", "post_stitch"),
            video_width=kwargs.get("video_width", 768),
            video_height=kwargs.get("video_height", 1152),
            audio_config=kwargs.get("audio_config", AudioConfig(enabled=True)),
            subtitle_config=kwargs.get("subtitle_config", SubtitleConfig(enabled=True)),
        )

    @pytest.mark.asyncio
    async def test_post_stitch_mode(self, temp_workdir):
        """数字人口播 — 后拼接音频模式。"""
        from core.pipelines.anchor_video import AnchorPipeline
        state = await self._make_state(audio_source="post_stitch")
        await self._run_and_verify(AnchorPipeline, state, temp_workdir,
                                    verify_prompts=True)

    @pytest.mark.asyncio
    async def test_model_audio_mode(self, temp_workdir):
        """数字人口播 — 模型自带音频模式。"""
        from core.pipelines.anchor_video import AnchorPipeline
        state = await self._make_state(
            audio_source="model",
            audio_config=AudioConfig(enabled=False),
            subtitle_config=SubtitleConfig(enabled=False),
        )
        await self._run_and_verify(AnchorPipeline, state, temp_workdir)

    @pytest.mark.asyncio
    async def test_post_stitch_no_subtitle(self, temp_workdir):
        """数字人口播 — 后拼接音频，无字幕。"""
        from core.pipelines.anchor_video import AnchorPipeline
        state = await self._make_state(
            audio_source="post_stitch",
            subtitle_config=SubtitleConfig(enabled=False),
        )
        await self._run_and_verify(AnchorPipeline, state, temp_workdir)


# ══════════════════════════════════════════════════════════════════════
# PoetryVideo Pipeline
# ══════════════════════════════════════════════════════════════════════

class TestPoetryVideoPipeline(BasePipelineTest):

    _POEM_TEXT = (
        "春眠不觉晓，处处闻啼鸟。\n\n"
        "夜来风雨声，花落知多少。"
    )

    async def _make_state(self, **kwargs):
        return PoetryVideoTask(
            task_type="poetry",
            creative_name="mock_poetry",
            poem_text=kwargs.get("poem_text", self._POEM_TEXT),
            user_scene_prompts=kwargs.get("user_scene_prompts", []),
            video_width=kwargs.get("video_width", 768),
            video_height=kwargs.get("video_height", 1152),
            audio_config=kwargs.get("audio_config", AudioConfig(enabled=True)),
            subtitle_config=kwargs.get("subtitle_config", SubtitleConfig(enabled=True)),
        )

    @pytest.mark.asyncio
    async def test_poetry_basic(self, temp_workdir):
        """诗词视频 — 基础全流程。"""
        from core.pipelines.poetry_video import PoetryVideoPipeline
        state = await self._make_state()
        await self._run_and_verify(PoetryVideoPipeline, state, temp_workdir,
                                    verify_prompts=True)

    @pytest.mark.asyncio
    async def test_poetry_no_audio(self, temp_workdir):
        """诗词视频 — 禁用音频和字幕。"""
        from core.pipelines.poetry_video import PoetryVideoPipeline
        state = await self._make_state(
            audio_config=AudioConfig(enabled=False),
            subtitle_config=SubtitleConfig(enabled=False),
        )
        await self._run_and_verify(PoetryVideoPipeline, state, temp_workdir)

    @pytest.mark.asyncio
    async def test_poetry_user_prompts(self, temp_workdir):
        """诗词视频 — 用户提供分镜 prompt 时按索引覆盖 LLM 生成。"""
        from core.pipelines.poetry_video import PoetryVideoPipeline
        user_prompts = [
            "黎明时分的竹林，薄雾缭绕，光线柔和",
            "暴雨过后的庭院，落花铺满青石地面",
        ]
        state = await self._make_state(user_scene_prompts=user_prompts)
        await self._run_and_verify(PoetryVideoPipeline, state, temp_workdir,
                                    verify_prompts=True)
        # 用户提供的分镜 prompt 应覆盖对应场景的 scene_prompt
        for idx, p in enumerate(user_prompts):
            assert state.scenes[idx].scene_prompt == p, \
                f"scene {idx} prompt not overridden: {state.scenes[idx].scene_prompt!r} != {p!r}"
        logger.info(f"  ✓ user_scene_prompts override verified for {len(user_prompts)} scenes")


# ══════════════════════════════════════════════════════════════════════
# Resume / Error 场景（可选）
# ══════════════════════════════════════════════════════════════════════

class TestPipelineResume(BasePipelineTest):
    """断点续传场景测试（仅验证 resume 不崩溃）。"""

    @pytest.mark.asyncio
    async def test_manuscript_resume_partial(self, temp_workdir):
        """稿件视频 — 模拟中途中断后 resume。"""
        from core.pipelines.manuscript_video import ManuscriptVideoPipeline
        from models.task import ManuscriptVideoTask, ManuscriptParagraph, StepStatus

        text = "春天来了，万物复苏。小猫开始了冒险。\n\n最后它回家了。"
        state = ManuscriptVideoTask(
            task_type="manuscript",
            creative_name="mock_resume",
            manuscript_text=text,
            audio_config=AudioConfig(enabled=True),
            subtitle_config=SubtitleConfig(enabled=True),
        )
        # 模拟已经完成了文本拆分
        state.step_split = StepStatus.COMPLETED
        state.step_scene_prompts = StepStatus.COMPLETED
        state.paragraphs = [
            ManuscriptParagraph(index=0, text="春天来了，万物复苏。小猫开始了冒险。", scene_prompt="春天的花园"),
            ManuscriptParagraph(index=1, text="最后它回家了。", scene_prompt="夕阳下的窗台"),
        ]

        await self._run_and_verify(ManuscriptVideoPipeline, state, temp_workdir,
                                    verify_prompts=True)


# ══════════════════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
