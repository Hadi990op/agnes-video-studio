# AGENTS.md — Agnes Video Generator v2.0

> **面向对象**：SoftwareCompany 团队（产品经理 / 架构师 / 工程师 / QA 工程师）
> **当前阶段**：🟢 规划完成 — 等待用户说"继续2.0版本开发"进入实现阶段
> **工作流**：标准 SOP（> 10 个源文件，多模块）
> **配套文档**：`docs/development_plan.md`（总计划）、`docs/system_design.md`（架构+任务）、`docs/test_plan.md`（测试流程）

---

## 〇、AI Agent 触发词

当用户在对话中说以下任一短语时，主理人应执行对应操作：

| 用户说法 | 主理人应执行的操作 | 说明 |
|---------|-------------------|------|
| **"继续2.0版本开发"** | 从 **Batch A** 开始分批执行（实现→验证→确认→下一批） | 进入实现阶段 |
| **"开始开发"** / **"开始实现"** | 同上 | 同义触发词 |
| **"继续下一批"** / **"继续 Batch X"** | 启动下一批次的实现 | 当前批次已确认后使用 |
| **"继续"** | 同上（需结合上下文确认指当前批次） | 模糊触发词，需确认 |
| **"只做 PRD"** / **"需求分析"** | 仅启动 `software-product-manager` | 部分工作流 |
| **"架构评审"** | 仅启动 `software-architect` | 部分工作流 |
| **"修复 Bug: ..."** | 启动 `software-engineer`（BugFix 快捷路径） | 跳过 PRD/架构 |

### 分批执行流程

```
用户说 "继续2.0版本开发"
       ↓
┌──────────────────────────────────────────────┐
│ 主理人启动 Batch A（T01，5 文件）              │
│   → software-engineer 实现                    │
│   → 工程师自验 bash start.sh + 主流程可用      │
│   → software-qa-engineer 验证（8 项检查）      │
│   → 向用户汇报结果，等待确认                    │
└──────────────────────────────────────────────┘
       ↓ 用户确认
┌──────────────────────────────────────────────┐
│ 主理人启动 Batch B（T02+T03，14 文件）         │
│   → software-engineer 实现                    │
│   → 工程师自验 bash start.sh + 主流程可用      │
│   → software-qa-engineer 验证（9 项检查）      │
│   → 向用户汇报结果，等待确认                    │
└──────────────────────────────────────────────┘
       ↓ 用户确认
┌──────────────────────────────────────────────┐
│ 主理人启动 Batch C（T04+T05，3 文件）          │
│   → software-engineer 实现                    │
│   → 工程师自验 bash start.sh + 主流程可用      │
│   → software-qa-engineer 验证（12 项检查）     │
│   → 向用户汇报结果，交付完成                    │
└──────────────────────────────────────────────┘
```

### 主理人每批操作清单

```
[ ] 1. 确认团队存在（software-agnes-refactor）
[ ] 2. 阅读 docs/development_plan.md 确认当前批次任务 + 验证清单
[ ] 3. 启动 software-engineer，下发当前批次任务（仅本批次，不跨批）
[ ] 4. 工程师完成后 → 核实 AGENTS.md 全局一致性审查清单中本批次相关条目
[ ] 5. 工程师自验 bash start.sh 可启动 + 主流程可用（不通过 → 修复后重新自验）
[ ] 6. 启动 software-qa-engineer，按验证清单逐项验证（含 start.sh + 主流程项）
[ ] 7. QA 全部通过 → 使用"每批完成确认模板"向用户汇报（含 start.sh + 主流程结果）
[ ] 8. QA 不通过（源码 Bug）→ 反馈工程师修复 → 重新验证（最多 2 轮）
[ ] 9. 用户确认后 → 继续下一批
```

---

## 一、项目定位

基于 Agnes AI 免费模型的视频生成工具，从单一"创意长视频"改造为 **三种任务类型** 的一站式 Web 应用。

## 二、技术栈（锁定，所有角色不可变更）

| 层 | 选型 | 约束 |
|------|------|------|
| 后端框架 | Python FastAPI + WebSocket | 保持 |
| 数据模型 | Pydantic v2 | 保持 |
| 视频处理 | moviepy + ffmpeg | 保持 |
| TTS | **edge_tts >= 6.1.0** | 新增，免费 |
| 字幕 | **srt >= 3.5.0** | 新增 |
| 前端 | 原生 HTML/CSS/JS + Tailwind CDN | 单文件 `static/index.html` |
| LLM | Agnes Chat API (`agnes-2.0-flash`) | 保持 |
| 图片模型 | `agnes-image-2.1-flash` | 保持 |
| 视频模型 | `agnes-video-v2.0` | 保持 |
| 日志 | `logging.getLogger(__name__)` | 严格遵守 |

## 三、目标目录结构（最终态）

```
agnes-video-generator/
├── server.py                         # [重写] 三种任务路由
├── start.sh                          # [保持]
├── requirements.txt                  # [修改] + edge_tts, srt
│
├── models/
│   ├── __init__.py                   # [修改]
│   └── task.py                       # [重写] TaskType + BaseTaskState + 3子类
│
├── core/
│   ├── __init__.py                   # [修改]
│   ├── config.py                     # [修改] +音频/字幕默认配置
│   ├── task_manager.py               # [修改] 泛化多类型
│   ├── screenwriter.py               # [保持+小改] 新增 generate_scene_prompt_for_paragraph()
│   │
│   ├── api/                          # [新增目录]
│   │   ├── __init__.py
│   │   ├── agnes_image.py            # 从 image_generator.py 迁移
│   │   ├── agnes_video.py            # 从 video_generator.py 迁移
│   │   └── agnes_chat.py             # 从 screenwriter 提取
│   │
│   ├── compositor/                   # [新增目录]
│   │   ├── __init__.py
│   │   ├── concatenator.py           # VideoConcatenator
│   │   └── processor.py              # VideoProcessor
│   │
│   ├── audio/                        # [新增目录]
│   │   ├── __init__.py
│   │   ├── tts.py                    # EdgeTTSEngine + SilentTTSEngine
│   │   └── subtitle.py               # SubtitleGenerator
│   │
│   └── pipelines/                    # [新增目录]
│       ├── __init__.py               # BasePipeline + 导出
│       ├── simple_video.py           # 类型1
│       ├── creative_video.py         # 类型2（从 pipeline.py）
│       └── manuscript_video.py       # 类型3
│
├── utils/
│   ├── __init__.py                   # [保持]
│   ├── image.py                      # [保持]
│   └── video.py                      # [保持]
│
├── static/
│   └── index.html                    # [重写] 三 Tab 架构
│
└── docs/
    ├── PRD_REFACTOR.md
    ├── system_design.md
    ├── development_plan.md
    ├── class-diagram.mermaid
    ├── sequence-diagram.mermaid
    └── test_plan.md
```

---

## 四、各角色工作说明

### 4.1 产品经理（许清楚）

**输入**：用户需求描述
**产出**：`PRD_REFACTOR.md`（增量 PRD）

**产出规范**：
- 产品目标（3-5 条）
- 用户故事（按任务类型分类）
- 需求池（P0/P1/P2 表格式）
- UI 设计概要（ASCII 布局图）
- 代码分层架构建议
- 待确认问题列表

**关键约束**：
- 默认输出简单 PRD（4 章节），除非用户明确要求竞品分析
- P0 需求必须包含：任务类型定义、API 调用方式、UI 交互说明
- 技术选型沿用现有栈，不可引入付费服务

---

### 4.2 架构师（高见远）

**输入**：PRD 文档（`PRD_REFACTOR.md`）
**产出**：
- `docs/system_design.md` — 完整系统设计 + 任务分解
- `docs/class-diagram.mermaid` — 类图
- `docs/sequence-diagram.mermaid` — 时序图

**产出规范（system_design.md 必须包含）**：

| 章节 | 内容 |
|------|------|
| 1. 实现方案与框架选型 | 核心技术挑战表格 + 框架选型 + 不引入的依赖 |
| 2. 完整文件列表 | 所有文件的相对路径 + 操作类型（新增/修改/重写/保持） |
| 3. 数据结构与接口 | 模型层级图 + 核心类说明 |
| 4. 程序调用流程 | 三种任务类型的流程描述 |
| 5. 待明确事项 | 识别 PRD 中的模糊点 |
| Part B: 依赖包 | requirements.txt 完整清单 |
| Part B: 任务列表 | 5 个有序任务，每个含：ID/优先级/依赖/源文件列表/产出说明 |
| Part B: 共享知识 | 日志规范/文件命名/错误处理/API响应格式/向后兼容 |
| Part B: 任务依赖图 | Mermaid graph TD |

**类图规范**：
- 用 `classDiagram` 描述：枚举 → 配置类 → 数据模型 → Service 类
- 每个类标注关键字段和类型

**时序图规范**：
- 用 `sequenceDiagram` 描述三种任务类型的完整调用链

---

### 4.3 工程师（寇豆码）

**输入**：架构设计 + 任务列表
**产出**：所有源文件代码

**工作流程**：

1. **按任务顺序实现**：T01 → T02 → T03 → T04 → T05（必须严格按依赖顺序）
2. **批量编写**：同一模块相关文件在一次 turn 中写完
3. **全部文件完成后** → 执行**全局一致性审查**
4. **自验 start.sh + 主流程**（不通过 → 修复后重新自验，这是硬性通过条件）
   - `bash start.sh` 可正常启动服务（Uvicorn 监听 8765 端口无报错）
   - 当前批次涉及的主流程可用（详见 `docs/development_plan.md` 该批次验证清单末尾的 start.sh + 主流程项）
   - 已有功能不被破坏（向后兼容别名/旧 import 路径等）

**全局一致性审查清单（必须逐项检查）**：

```
[ ] 导入路径：所有 import 使用新的目录结构（core.api.xxx / core.compositor.xxx / core.audio.xxx / core.pipelines.xxx）
[ ] 类名命名：AgnesImageAPI / AgnesVideoAPI / AgnesChatAPI（非旧名）
[ ] 日志前缀：严格使用规范格式 [Simple]/[Manuscript]/[TTS]/[Subtitle]/[Compositor]/[AgnesImage]/[AgnesVideo]/[AgnesChat]
[ ] 向后兼容：TaskManager.load() 处理无 task_type 的旧数据
[ ] Screenwriter：使用 AgnesChatAPI（非直接 requests）
[ ] 旧文件处理：image_generator.py / video_generator.py / pipeline.py 已删除或仅保留兼容别名
[ ] 音频字幕：EdgeTTSEngine + SubtitleGenerator 接口与 Pipeline 集成正确
[ ] 稿件拆段：split_manuscript() 使用时间估算（4字/秒），不拆句子
[ ] Server 路由：三种 POST 端点 + resume 根据 task_type 选择 Pipeline
[ ] 前端：三个 Tab 各独立渲染，i18n 补全 7 种语言
[ ] requirements.txt：包含 edge_tts >= 6.1.0, srt >= 3.5.0
[ ] Video-audio padding：≤ 1 秒
```

审查结果：`IS_PASS: YES` 或 `IS_PASS: NO`（附问题列表）。最多 2 轮。

**代码风格约束**：
- Python：Google 风格 docstring，类型注解，async/await 用于 IO
- 前端：ES6+，保持与现有代码一致的函数式风格，不引入框架
- 所有文件 UTF-8 编码

---

### 4.4 QA 工程师（严过关）

**输入**：工程师完成的代码
**产出**：`docs/test_plan.md`（首次）+ 测试执行报告

**测试策略（三层）**：

#### 第一层：静态分析
```
[ ] Python 语法检查：python -m py_compile 所有 .py 文件
[ ] 导入验证：python -c "from core.api.agnes_video import AgnesVideoAPI" 等
[ ] 前端语法：HTML/JS 无语法错误
```

#### 第二层：单元测试（核心模块）

| 模块 | 测试点 | 测试方法 |
|------|--------|---------|
| `models/task.py` | TaskType 枚举、BaseTaskState 子类实例化、JSON 序列化/反序列化 | Python script |
| `core/audio/tts.py` | EdgeTTSEngine.generate() 返回 (audio_path, sub_maker) | 需要网络，skip 标记 |
| `core/audio/subtitle.py` | cues_to_srt() 输出合法 SRT 格式 | 离线可测 |
| `manuscript_video.py` | split_manuscript() 拆段算法 | 边界测试：空文本、单句、超长句 |
| `core/config.py` | get_default_audio_config() 返回正确结构 | 离线可测 |
| `core/task_manager.py` | 旧数据兼容（无 task_type → CREATIVE） | 离线可测 |

#### 第三层：集成测试（服务端点）

| 端点 | 测试点 |
|------|--------|
| `GET /` | 返回 200，包含三 Tab HTML 结构 |
| `GET /api/config` | 返回 ok: true |
| `POST /api/tasks/simple` | 参数校验、返回 task_id |
| `POST /api/tasks/creative` | 参数校验、返回 task_id |
| `POST /api/tasks/manuscript` | 参数校验、返回 task_id |
| `GET /api/tasks` | 列表包含三种类型 |
| `GET /api/tasks/{id}` | 返回任务详情含 task_type |

**智能路由判定**（每轮测试后）：

| 发现 | 处理 |
|------|------|
| 源码 Bug（逻辑错误、接口不匹配） | → 反馈给工程师（附具体错误和文件路径） |
| 测试代码 Bug（断言错误、mock 不当） | → QA 自行修复 |
| 全部通过 | → `ALL_PASS: YES` |

**最多 2 轮测试周期**。2 轮仍不过 → 输出遗留问题清单。

---

## 五、测试验证流程（完整）

```
工程师完成代码
       ↓
┌──────────────────────────────────────┐
│ QA 第 1 轮（全面验证）                │
│                                      │
│ 1. 静态分析（语法 + 导入）            │
│ 2. 单元测试（核心模块 6 项）           │
│ 3. 集成测试（7 个端点）               │
│ 4. 手动验收（前端 Tab 切换 + 表单）    │
│                                      │
│ 结果判定：                            │
│  ├─ 源码 Bug → 反馈工程师              │
│  ├─ 测试 Bug → QA 自修复              │
│  └─ ALL_PASS → 交付                   │
└──────────────────────────────────────┘
       ↓（如有源码 Bug）
工程师修复 → QA 第 2 轮（回归验证）
       ↓
┌──────────────────────────────────────┐
│ QA 第 2 轮（回归）                    │
│                                      │
│ 1. 重新运行失败测试                    │
│ 2. 验证修复是否引入新问题              │
│                                      │
│ 结果判定：                            │
│  ├─ ALL_PASS → 交付                   │
│  └─ 仍有失败 → 输出遗留问题清单 + 建议  │
└──────────────────────────────────────┘
```

---

## 六、共享知识规范

### 6.1 日志前缀

| 前缀 | 模块 | 日志级别建议 |
|------|------|------------|
| `[Startup]` | server.py | INFO |
| `[WS]` | WebSocket | INFO |
| `[Resume]` | server.py resume | INFO |
| `[Stop]` | server.py stop | INFO |
| `[Pipeline]` | creative_video.py | INFO |
| `[Simple]` | simple_video.py | INFO |
| `[Manuscript]` | manuscript_video.py | INFO |
| `[TTS]` | tts.py | INFO |
| `[Subtitle]` | subtitle.py | INFO |
| `[Compositor]` | compositor/ | INFO |
| `[AgnesImage]` | agnes_image.py | INFO |
| `[AgnesVideo]` | agnes_video.py | INFO |
| `[AgnesChat]` | agnes_chat.py | INFO |
| `[TaskManager]` | task_manager.py | INFO |
| `[Screenwriter]` | screenwriter.py | INFO |

### 6.2 错误处理

| 场景 | 策略 |
|------|------|
| LLM 调用 | 重试 3 次，间隔 15s 递增 |
| 视频提交 | 重试 5 次，间隔 30s 递增 |
| 视频轮询 | 间隔 15s，每 10 次输出日志 |
| PipelineShutdown | 所有流水线统一处理，落盘当前状态 |
| TTS 失败 | 降级为静音 + 字幕 |

### 6.3 向后兼容

- `TaskManager.load()` 自动将无 `task_type` 字段的旧数据识别为 `CreativeVideoTask`
- 旧 `task_state.json` 字段名保持不变
- 旧 `_find_dir_name()` 逻辑保持不变

### 6.4 API 响应格式

```json
// 成功
{"ok": true, "task_id": "...", ...}

// 失败
HTTPException(status_code=4xx/5xx, detail="...")
```

### 6.5 WebSocket 消息格式

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

### 6.6 视频-音频同步策略

```python
# 每段最终时长
final_duration = max(audio_duration + 1.0, original_video_duration)
# padding ≤ 1 秒，不足时尾帧 freeze
```

### 6.7 稿件拆段算法

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

## 七、关键决策记录

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

## 八、阶段状态

| 阶段 | 批次 | 状态 | 产出 |
|------|------|------|------|
| PRD 产品需求 | — | ✅ 完成 | `PRD_REFACTOR.md` |
| 系统设计 | — | ✅ 完成 | `docs/system_design.md` + `class-diagram.mermaid` + `sequence-diagram.mermaid` |
| 开发计划 | — | ✅ 完成 | `docs/development_plan.md` |
| **Batch A：基础设施** | T01（5文件） | ⏳ **等待启动** | models/task.py, config.py, task_manager.py... |
| **Batch B：组件+流水线** | T02+T03（14文件） | ⏳ 等待 Batch A | api/, audio/, compositor/, pipelines/ |
| **Batch C：服务端+前端** | T04+T05（3文件） | ⏳ 等待 Batch B | server.py, index.html |
| QA 最终验收 | — | ⏳ 未开始 | — |

> **下一步**：当用户说"继续2.0版本开发"时，主理人从 **Batch A** 开始，走 实现→验证→确认→下一批 循环。
>
> **禁止一次性全量实现**。每批完成后必须经过 QA 验证并通过用户确认才能进入下一批。

---

*文档版本：v3.1 | 更新日期：2025-06-14 | 执行模式：分批（含增量可运行验证） | 配套：docs/development_plan.md*
