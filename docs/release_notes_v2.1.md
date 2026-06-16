# Release v2.1 — 代码审查修复 + 回归测试框架 + 质量改进

> 发布日期：2026-06-16

## 概述

v2.1 聚焦代码质量和工程健壮性，基于完整的代码审查流程（24 个问题）逐项修复，并引入自动化回归测试框架确保长期稳定性。

---

## 代码审查修复

基于 `docs/code_review_report.md` 的 24 个问题全部修复：

### 高风险 (H1-H6)
- **H1** — `agnes_chat.py` API Key 硬编码泄漏 → 统一从 `config.py` 读取
- **H2** — `server.py` 文件上传路径穿越 → 使用 `os.path.basename` 安全拼接
- **H3** — `concatenator.py` 字幕叠加缺乏字体回退 → 实现 `resolve_font_path` CJK 回退
- **H4** — `processor.py` shell 注入 → 使用列表参数替代 `shell=True`
- **H5** — `subtitle.py` moviepy `write_videofile` 日志泄漏 → 重定向到 `devnull`
- **H6** — `screenwriter.py` JSON 解析失败 → 加入 LLM 重试与 fallback 解析

### 中风险 (M1-M10)
- 索引/越界防御（M1-M3）
- 异常捕获范围过宽 → 精细化（M4-M5）
- 任务目录路径规范化（M6）
- HTTP 超时统一化（M7）
- 任务状态竞争条件（M8）
- TTS 文件句柄泄漏（M9）
- 前端 i18n 变量冲突（M10）

### 低风险 (L1-L8)
- 自动化单元测试框架（L1）
- Typo 修复（L2-L3）
- 文档冗余清理（L4-L5）
- AGENTS.md 与代码对齐（L6）
- 废弃文件清理（L7-L8）

---

## 回归测试框架

- **9 场景并发回归**（3 简单 + 4 创意 + 2 稿件）
- 加权信号量控制并行度（总权重 ≤ 10，留 50% API 余量）
- 增量 JSON 报告 + Markdown 可读报告
- 断点续传 / 快速验证模式
- `--cleanup` 安全清理回归产物

### 端点验证 (E1-E9)
全部 9 个端点自动验证：首页、配置、三种任务创建、任务查询、续传、停止

### 产物验证 (F1-F7, R1-R10)
- `final_video.mp4` 存在性 + 非空 + 时长 + 分辨率
- 音频轨道 + whisper ASR 语音内容匹配
- SRT 字幕条目验证
- 断点续传产物完整性

---

## 其他改进

- **字幕多行换行** — 动态 `max_chars_per_line`，CJK 标点优先断行，`method="caption"` 渲染
- **TTS** — 自动 2.5 倍音量补偿，边缘情况错误处理
- **拼接器** — 单视频短路优化，字幕叠加失败降级（不中断生成）
- **start.sh** — venv 自动创建、依赖安装、macOS 自动打开浏览器
- **需求文件** — 锁定 `edge_tts>=7.0.0`, `srt>=3.5.0`, `moviepy>=2.0.0`
- **配置** — API Key 清除功能，字体路径增强回退
- **静态分析集成** — 每个 `Taskfile` 含 `ruff` + `mypy` 检查

---

## 变更统计

```
26 files changed, 1,611 insertions(+), 235 deletions(-)
```

### 新增/删除文件
| 文件 | 操作 | 说明 |
|------|------|------|
| `docs/code_review_report.md` | +新增 | 24 个代码审查问题文档 |
| `docs/release_notes_v2.0.md` | +新增 | v2.0 发版说明 |
| `tests/test_core.py` | +新增 | 428 行自动化单元测试 |
| `test_ref.png` / `test_end.png` | +新增 | 回归测试素材 |
| `_test_reset.py` | -删除 | 废弃测试脚本 |
| `start.sh` | 重构 | 一键启动，自动 venv + 依赖 + 浏览器 |

---

## 升级说明

从 v2.0 升级：
```bash
git pull
.venv/bin/pip install -r requirements.txt
./start.sh
```

运行回归测试：
```bash
.venv/bin/python scripts/regression_runner.py --auto-start
```
