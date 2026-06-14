# AGENTS.md — Agnes Video Generator v2.0

> **面向对象**：SoftwareCompany 团队（产品经理 / 架构师 / 工程师 / QA 工程师）
> **当前阶段**：🟢 **开发完成（v2.0） — 维护模式**
> **配套文档**：`docs/system_design.md`（架构）、`docs/regression_test_plan.md`（大版本回归）

---

## 〇、AI Agent 触发词

| 用户说法 | 主理人应执行的操作 | 说明 |
|---------|-------------------|------|
| **"修复 Bug: ..."** | 启动 `software-engineer`（BugFix 快捷路径） | 定位→修复→自验→汇报 |
| **"执行大版本回归"** | 按 `docs/regression_test_plan.md` 执行全量回归测试 | 9 场景并发 + 端点验证 |
| **"新增功能: ..."** | 启动 `software-product-manager` → 需求分析 | 增量功能开发 |
| **"需求分析" / "只做 PRD"** | 启动 `software-product-manager` | 部分工作流 |
| **"架构评审"** | 启动 `software-architect` | 部分工作流 |

---

## 一、项目定位

基于 Agnes AI 免费模型的视频生成工具，支持 **三种任务类型** 的一站式 Web 应用：
- **简单视频**：单次调用 Agnes Video API，暴露全部参数的结构化 UI
- **创意长视频**：AI 编剧 → 分镜图生成 → 视频生成 → edge_tts 旁白 + 字幕叠加 → 拼接
- **稿件长视频**：长文本 → 时间估算拆段 → AI 场景 prompt → 逐段视频生成 → TTS+字幕 → 拼接

---

## 二、技术栈

| 层 | 选型 |
|------|------|
| 后端框架 | Python FastAPI + WebSocket |
| 数据模型 | Pydantic v2 |
| 视频处理 | moviepy + ffmpeg |
| TTS | edge_tts >= 6.1.0 |
| 字幕 | srt >= 3.5.0 |
| 前端 | 原生 HTML/CSS/JS + Tailwind CDN（单文件 `static/index.html`） |
| LLM | Agnes Chat API (`agnes-2.0-flash`) |
| 图片模型 | `agnes-image-2.1-flash` |
| 视频模型 | `agnes-video-v2.0` |
| 日志 | `logging.getLogger(__name__)` |

---

## 三、目录结构

```
agnes-video-generator/
├── server.py                         # FastAPI 主服务，三种任务路由
├── start.sh                          # 启动脚本
├── requirements.txt                  # 依赖（含 edge_tts, srt）
│
├── models/
│   ├── __init__.py
│   └── task.py                       # TaskType + BaseTaskState + 3 子类
│
├── core/
│   ├── __init__.py
│   ├── config.py                     # 音频/字幕默认配置
│   ├── task_manager.py               # 任务状态持久化，向后兼容
│   ├── screenwriter.py               # 编剧 Agent
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── agnes_image.py            # 图片生成 API
│   │   ├── agnes_video.py            # 视频生成 API
│   │   └── agnes_chat.py             # LLM Chat API
│   │
│   ├── compositor/
│   │   ├── __init__.py
│   │   ├── concatenator.py           # 视频拼接
│   │   └── processor.py              # 视频处理（缩放/帧提取/静音）
│   │
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── tts.py                    # EdgeTTSEngine + SilentTTSEngine
│   │   └── subtitle.py               # 字幕生成与叠加
│   │
│   └── pipelines/
│       ├── __init__.py               # BasePipeline
│       ├── simple_video.py           # 类型 1
│       ├── creative_video.py         # 类型 2
│       └── manuscript_video.py       # 类型 3
│
├── utils/
│   ├── __init__.py
│   ├── image.py
│   └── video.py
│
├── static/
│   └── index.html                    # 三 Tab 前端
│
├── scripts/
│   └── regression_runner.py          # 大版本回归测试脚本
│
└── docs/
    ├── system_design.md
    ├── regression_test_plan.md
    ├── class-diagram.mermaid
    └── sequence-diagram.mermaid
```

---

## 四、BugFix 工作流

用户说 **"修复 Bug: ..."** 时，主理人按以下流程执行：

```
1. 定位
   - 阅读用户描述的 bug 现象
   - 用 codegraph / grep 定位到相关文件和代码行
   - 复现 bug（如能通过 API 调用复现）

2. 修复
   - 启动 software-engineer 执行修复
   - 确保修复不违反 AGENTS.md 中的共享知识规范

3. 自验
   - bash start.sh 正常启动（Uvicorn 监听 8765 端口无报错）
   - 受影响的端点 curl 验证返回正确结果
   - 已有功能不被破坏

4. 汇报
   - 向用户说明：根因、修复方案、涉及文件
   - 附 curl 验证结果
```

---

## 五、大版本回归测试

用户说 **"执行大版本回归"** 时，主理人加载 `docs/regression_test_plan.md` 执行。

### 流程概览

```
用户说 "执行大版本回归"
       ↓
┌───────────────────────────────────────────┐
│ 1. 准备 → git status + 素材检查 + 启动服务   │
│ 2. 并发执行 → 9 场景（加权信号量，总权重≤10） │
│ 3. 自动验证 → F1-F7、R1-R10、E1-E9          │
│ 4. 报告输出 → JSON + 可读报告                │
│ 5. 手动验证项 → 请用户确认音频/字幕/断点续传   │
└───────────────────────────────────────────┘
```

### 9 场景矩阵

| ID | 类型 | 场景 | 权重 |
|----|------|------|------|
| S1 | 简单视频 | 纯文本 t2v | 1 |
| S2 | 简单视频 | 图生视频 ti2vid | 1 |
| S3 | 简单视频 | 关键帧动画 keyframes | 1 |
| C1 | 创意视频 | 纯文字+独立+无配音 | 3 |
| C2 | 创意视频 | 带参考图+关键帧+无配音 | 3 |
| C3 | 创意视频 | 参考图生成尾帧+关键帧+无配音 | 3 |
| C4 | 创意视频 | 独立场景+配音字幕验证 | 4 |
| M1 | 稿件视频 | 短稿件+配音 | 4 |
| M2 | 稿件视频 | 短稿件+自定义字幕 | 4 |

### 执行脚本

```bash
# 完整回归
python scripts/regression_runner.py --auto-start

# 断点续传
python scripts/regression_runner.py --resume --auto-start

# 仅验证已存在产物
python scripts/regression_runner.py --quick
```

---

## 六、各角色工作说明

### 6.1 产品经理（许清楚）

**输入**：用户需求描述（新增功能）
**产出**：`PRD_REFACTOR.md`（增量 PRD）

**产出规范**：
- 产品目标（3-5 条）
- 用户故事
- 需求池（P0/P1/P2）
- UI 设计概要（ASCII 布局图）
- 技术选型沿用现有栈，不可引入付费服务

---

### 6.2 架构师（高见远）

**输入**：PRD 文档
**产出**：`docs/system_design.md` 增量更新

---

### 6.3 工程师（寇豆码）

**输入**：Bug 描述 / 架构设计
**产出**：修复代码或新功能代码

**代码风格约束**：
- Python：Google 风格 docstring，类型注解，async/await 用于 IO
- 前端：ES6+，不引入框架
- 所有文件 UTF-8 编码

---

### 6.4 QA 工程师（严过关）

**输入**：工程师完成的代码
**产出**：测试验证报告

**验证层次**：

#### 第一层：静态分析
```
[ ] Python 语法检查：python -m py_compile 所有 .py 文件
[ ] 导入验证：python -c "from core.api.agnes_video import AgnesVideoAPI" 等
[ ] 前端语法：HTML/JS 无语法错误
```

#### 第二层：单元测试
| 模块 | 测试点 |
|------|--------|
| `models/task.py` | 序列化/反序列化 |
| `core/audio/subtitle.py` | SRT 格式输出 |
| `manuscript_video.py` | split_manuscript() 拆段算法 |
| `core/config.py` | 默认配置结构 |
| `core/task_manager.py` | 旧数据兼容 |

#### 第三层：集成测试
| 端点 | 测试点 |
|------|--------|
| `GET /` | 返回 200，三 Tab HTML |
| `GET /api/config` | 返回 ok: true |
| `POST /api/tasks/simple` | 参数校验 |
| `POST /api/tasks/creative` | 参数校验 |
| `POST /api/tasks/manuscript` | 参数校验 |
| `GET /api/tasks` | 列表含三种类型 |
| `GET /api/tasks/{id}` | 返回 task_type |

---

## 七、共享知识规范

### 7.1 日志前缀

| 前缀 | 模块 |
|------|------|
| `[Startup]` | server.py |
| `[WS]` | WebSocket |
| `[Resume]` | server.py resume |
| `[Stop]` | server.py stop |
| `[Pipeline]` | creative_video.py |
| `[Simple]` | simple_video.py |
| `[Manuscript]` | manuscript_video.py |
| `[TTS]` | tts.py |
| `[Subtitle]` | subtitle.py |
| `[Compositor]` | compositor/ |
| `[AgnesImage]` | agnes_image.py |
| `[AgnesVideo]` | agnes_video.py |
| `[AgnesChat]` | agnes_chat.py |
| `[TaskManager]` | task_manager.py |
| `[Screenwriter]` | screenwriter.py |

### 7.2 错误处理

| 场景 | 策略 |
|------|------|
| LLM 调用 | 重试 3 次，间隔 15s 递增 |
| 视频提交 | 重试 5 次，间隔 30s 递增 |
| 视频轮询 | 间隔 15s，每 10 次输出日志 |
| PipelineShutdown | 所有流水线统一处理，落盘当前状态 |
| TTS 失败 | 降级为静音 + 字幕 |

### 7.3 向后兼容

- `TaskManager.load()` 自动将无 `task_type` 字段的旧数据识别为 `CreativeVideoTask`
- 旧 `task_state.json` 字段名保持不变

### 7.4 API 响应格式

```json
// 成功
{"ok": true, "task_id": "...", ...}

// 失败
HTTPException(status_code=4xx/5xx, detail="...")
```

### 7.5 WebSocket 消息格式

```json
{
  "type": "progress",
  "task_id": "...",
  "step": "video_split",
  "status": "running",
  "message": "正在拆分文本...",
  "progress": 0.3,
  "data": {"current": 2, "total": 5}
}
```

### 7.6 视频-音频同步策略

```python
final_duration = max(audio_duration + 1.0, original_video_duration)
# padding ≤ 1 秒，不足时尾帧 freeze
```

### 7.7 稿件拆段算法

```python
def split_manuscript(text: str) -> list[dict]:
    """
    1. 按句号/问号/感叹号拆分为候选句子
    2. 每个句子 est_duration = len(text) / 4.0
    3. 贪心合并：累计时长 ∈ [5, 12] 秒
    4. 长句（> 12s）接受，不拆
    5. 短句（< 5s）合并到前一段
    """
```

---

## 八、关键决策记录

| ID | 决策 | 详情 |
|----|------|------|
| D1 | 稿件拆段 | 时间估算 4 字/秒，5-12s/段，不拆句子 |
| D2 | 稿件 scene prompt | AI 生成英文 prompt，原文作旁白+字幕 |
| D3 | TTS 默认语音 | `zh-CN-XiaoxiaoNeural` |
| D4 | 视频 padding | ≤ 1 秒 |
| D5 | 简单视频 prompt | 结构化暴露 Agnes API 全部 8 个参数，不做 AI 增强 |
| D6 | 旧数据兼容 | 无 task_type → CREATIVE |
| D7 | 多语言 | 保持 7 语言 (zh/en/ru/ja/ko/ms/id) |
| D8 | TTS 付费方案 | 不引入，仅用 edge_tts |

---

*文档版本：v4.0 | 更新日期：2026-06-14 | 阶段：🟢 开发完成（v2.0）— 维护模式*
