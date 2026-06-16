# Release v2.0 — 三流水线架构 + 多语言 Web UI

> 发布日期：2026-06-15

## 概述

v2.0 是从单文件脚本到工程化架构的全面重构，引入三种独立的视频生成流水线、四层后端架构、WebSocket 实时进度推送、7 语言国际化前端。

---

## 新功能

### 三种任务类型
- **简单视频** — 单 prompt → 单视频，暴露 Agnes API 全部 9 个参数（t2v/i2v/ti2vid/keyframes）
- **创意长视频** — AI 编剧 → 分镜图 → 逐场景视频 → edge_tts 旁白配音 → 细粒度字幕 → 拼接
- **稿件长视频** — 长文本拆段 → AI 场景 prompt → 逐段视频 → 统一 TTS+字幕 → 拼接

### 架构重构
- `core/api/` — Agnes Chat / Image / Video API 封装，含重试与轮询
- `core/audio/` — edge_tts 引擎（词级时间戳） + SRT 字幕生成 + moviepy 叠加
- `core/compositor/` — 视频拼接 + 缩放/帧提取/静音音频生成
- `core/pipelines/` — 三种流水线实现（simple/creative/manuscript）
- `models/` — Pydantic v2 数据模型，PERSISTENT 任务状态持久化

### Web UI
- 三 Tab 前端（简单/创意/稿件），Tailwind CDN 单页面
- 7 语言支持：中文/English/Русский/日本語/한국어/Bahasa Melayu/Bahasa Indonesia
- WebSocket 实时进度推送
- 任务暂停/续传/停止

### 字幕系统
- edge_tts 词级时间戳 → 细粒度 SRT 分组
- CJK 多行换行（标点处断行）
- `method="caption"` 渲染，支持描边/背景/位置自定义

### 其他
- 一键启动脚本 `start.sh`
- `docs/system_design.md` 系统设计文档
- 3 个演示视频嵌入 README

---

## 变更统计

```
40 files changed, 11,268 insertions(+), 2,792 deletions(-)
```

### 新增文件
| 文件 | 说明 |
|------|------|
| `core/pipelines/` | 三种流水线（simple/creative/manuscript） |
| `core/api/` | Agnes API 封装层 |
| `core/audio/` | TTS + 字幕引擎 |
| `core/compositor/` | 视频合成/处理 |
| `models/task.py` | 三种任务子类型数据模型 |
| `scripts/regression_runner.py` | 回归测试脚本 |
| `docs/system_design.md` | 系统设计文档 |
| `docs/regression_test_plan.md` | 测试计划 |

---

## 升级说明

- Python 3.10+ 必需
- 新增依赖：`edge_tts>=6.1.0`, `srt>=3.5.0`
- 运行 `./start.sh` 一键启动，或 `.venv/bin/pip install -r requirements.txt && .venv/bin/python server.py`
