# 配置参考

系统的配置分散在四处，优先级由高到低：**CLI 参数 > 环境变量 > 项目 YAML/JSON > 代码常量**。本文档汇总全部可调项及其代码位置。

---

## 1. 环境变量

系统**不需要任何模型供应商的 API key**。生成与审稿都通过当前环境的智能体 CLI 完成，认证由该 CLI 自己负责（例如 Claude Code 的 OAuth 登录态）。

### 智能体选择

| 变量 | 作用 | 默认 |
|------|------|------|
| `META_WRITING_AGENT_CMD` | 完整命令，`shlex.split` 后直接使用。最高优先级，也是逃生舱 | 无 |
| `META_WRITING_AGENT` | `claude` 或 `codex`；值非法或命令不在 PATH 上则报错 | 无 |
| `META_WRITING_AGENT_TIMEOUT` | 单次调用超时（秒）；非法值或 ≤0 时回落到默认 | `900` |

探测优先级：`META_WRITING_AGENT_CMD` > `META_WRITING_AGENT` > PATH（`claude` 优先，其次 `codex`）> 抛 `AgentNotFoundError`。

```powershell
# 通常什么都不用设——PATH 上有 claude 就够了
$env:META_WRITING_AGENT = "codex"          # 强制用 codex
$env:META_WRITING_AGENT_CMD = "/opt/my-agent --flag"   # 完全自定义
$env:META_WRITING_AGENT_TIMEOUT = "1800"   # 写超长章节时放宽
```

验证当前会解析到哪个智能体：

```powershell
python -X utf8 -c "from meta_writing.llm import detect_agent; s=detect_agent(); print(s.kind, s.argv)"
```

详见 [`../architecture/agent-backend.md`](../architecture/agent-backend.md)。

## 2. 项目级配置

### `.meta-writing-project.json`

```json
{ "name": "rescue-male-lead" }
```

只记录项目名。文件缺失时 `read_project_metadata()` 返回 `None`，项目名回落为目录名。

### `story_data/story_core.yaml`

影响运行行为的字段（完整定义见 [`story-bible-schema.md`](story-bible-schema.md)）：

| 字段 | 作用 | 无值时的兜底 |
|------|------|-------------|
| `chapter_target_chars` | 扩写目标字数 | `TARGET_CHAPTER_CHARS = 10000` |
| `chapter_min_chars` | 触发扩写的下限 | `MIN_CHAPTER_CHARS = 7000` |
| `foreshadowing_max_age_chapters` | 伏笔告警阈值 | `20` |
| `target_satisfaction_type` | 参与风格档案识别 | `""` |

### `creator_guidance.md`

长期创作指导，被合并进**全部** agent 的提示词，并参与风格档案自动识别。合并顺序：

```python
merged = "\n\n".join([creator_guidance.md 的内容, --guidance 传入的内容])
```

### `learned_rules.md`

累积的风格与连续性规则，由人维护。

### `.meta-writing/workspace.json`

```json
{ "current_project": "rescue-male-lead" }
```

---

## 3. 代码常量

以下阈值目前**硬编码在源码里，无法通过配置文件调整**。修改需改代码并同步更新测试。

### 评分体系 — [`editorial_scorecard.py`](../../meta_writing/editorial_scorecard.py)

| 常量 | 值 | 含义 |
|------|----|------|
| `EDITORIAL_PASS_THRESHOLD` | `8.0` | 综合分达标线 |
| `EDITORIAL_DIMENSION_FLOOR` | `7.0` | 单维地板分，任一维低于此值即不通过 |
| `EDITORIAL_MIN_IMPROVEMENT` | `0.2` | 判定「有进步」的最小分差 |
| `EDITORIAL_STAGNATION_PATIENCE` | `2` | 连续多少轮无进步即判停滞 |

维度权重 `DIMENSION_WEIGHTS`：

| 维度 | 权重 |
|------|------|
| `plot_tension` 剧情张力与节奏 | 0.30 |
| `characters` 人物塑造与互动 | 0.25 |
| `info_design` 信息量与暗线设计 | 0.20 |
| `language` 语言与描写质感 | 0.15 |
| `instruction_fit` 指令满足与完成度 | 0.10 |

调参指引见 [`../operations/editorial-scorecard-maintenance.md`](../operations/editorial-scorecard-maintenance.md)。

### 流水线 — [`orchestrator.py`](../../meta_writing/orchestrator.py)

| 常量 | 值 |
|------|----|
| `MAX_REVISION_ITERATIONS` | `5` |


### 上下文预算 — [`compressor.py`](../../meta_writing/story_bible/compressor.py)

| 参数 | 值 | 说明 |
|------|----|------|
| `StoryBibleCompressor(token_budget=…)` | `15000` | 构造参数，编排层用默认值 |
| 完整档案的角色数（`summarized` 级） | 前 3 位 | `active_names[:3]` |
| 时间线回看章数 | `full` 10 / `summarized` 5 | — |
| 爽点排期条数 | 5 | `upcoming[:5]` |

### 字数 — [`agents/writer.py`](../../meta_writing/agents/writer.py)

| 常量 | 值 |
|------|----|
| `MIN_CHAPTER_CHARS` | `7000` |
| `TARGET_CHAPTER_CHARS` | `10000` |

被 `story_core.yaml` 的对应字段覆盖。`meta-writing init` 的交互默认是 2000 字，与这两个常量差距很大——**建议每个项目都显式设置**，不要依赖兜底。

### 智能体后端 — [`llm.py`](../../meta_writing/llm.py)

| 常量 | 值 |
|------|----|
| `MAX_RETRIES` | `3` |
| `RETRY_BACKOFF_BASE` | `2.0`（退避 2/4/8 秒） |
| `DEFAULT_AGENT_TIMEOUT_SECONDS` | `900`（可经 `META_WRITING_AGENT_TIMEOUT` 覆盖） |
| `SUPPORTED_AGENTS` | `("claude", "codex")` |
| `CLAUDE_DISALLOWED_TOOLS` | 9 个工具全禁 |

各 agent 传入的 `max_tokens` 与 `temperature`：

| Agent | max_tokens | temperature |
|-------|-----------|-------------|
| Planner | 4096 | 0.8 |
| Planner（JSON 修复重试） | 4096 | 0.1 |
| Writer 写作 / 扩写 | 16384 | 0.7 |
| Writer 修订 | 16384 | 0.5 |
| Continuity / Style / Theme | 4096 | 0.3 |

> `max_tokens` 被智能体后端**忽略**（输出长度由当前智能体决定）；`temperature` 被**语义化**成提示词指令而非采样温度。详见 [`../architecture/agent-backend.md §4`](../architecture/agent-backend.md)。

### 向量存储 — [`vector_store/store.py`](../../meta_writing/vector_store/store.py)

| 常量 | 值 |
|------|----|
| `CHUNK_MIN_SIZE` / `CHUNK_TARGET_SIZE` / `CHUNK_MAX_SIZE` | 300 / 700 / 1200 |
| 嵌入模型 | `BAAI/bge-m3` |

当前无调用方。

---

## 4. 风格档案

[`prompt_profiles.py`](../../meta_writing/prompt_profiles.py) 的档案**按关键词自动识别**，无法在配置文件里指定。识别输入是 `creator_guidance` 合并文本 + `target_satisfaction_type`。

| 档案 | 触发关键词（命中任一） |
|------|----------------------|
| `literary_microfeel` | 克制美学、微感、留白、纯感官、物体记录时间、不解释 |
| `tomato_romance` | 番茄、高梗密度、快节奏、强情绪、系统向、打脸、吐槽、爽点、拉扯、女频 |
| `generic` | （以上都不命中时的兜底） |

**识别顺序是固定的**：先查文学关键词，再查番茄关键词。两组关键词同时命中时，`literary_microfeel` 优先。

要强制某个档案，最直接的办法是在 `creator_guidance.md` 里写入对应关键词。

每个档案可配置：

| 字段 | 作用 |
|------|------|
| `planner_notes` / `writer_notes` / `expansion_notes` / `revision_notes` / `continuity_notes` | 追加到对应 agent 的 system prompt |
| `negative_examples_profile` | 指定注入哪组反例；为 `None` 则不注入 |
| `third_editor_mode` | `story` 或 `literary_theme`，决定 ThemeAgent 用哪套提示词 |

> `PromptProfile` 还有一个 `third_editor_enabled` 字段，三个档案都是 `True`，且**当前无任何代码读取它**——`orchestrator.py` 无条件调用 ThemeAgent。它是自动链路移除后遗留的字段。

---

## 5. 已知的配置陷阱

| 陷阱 | 后果 | 规避 |
|------|------|------|
| 智能体 CLI 未登录 | 调用返回 `Not logged in`，三次重试后抛 `AgentInvocationError` | 先在终端跑一次 `claude -p "hi"` 确认登录态 |
| 期望用 `--bare` 提速 | 该参数把认证限制为 `ANTHROPIC_API_KEY`，会绕开 OAuth 登录态 | 代码已禁止使用，不要自行加回 |
| 在 Claude Code 会话里跑 `generate` | 嵌套智能体调用，能跑通但更慢更贵 | 在普通终端运行 |
| codex 适配器未经实测 | ECS 上可能不兼容 | 用 `META_WRITING_AGENT_CMD` 兜底 |
| 言情项目期待伏笔寿命 15 | `init` 的查表键 `言情` 不是合法 `Genre` 值，实得 20 | 手动填 `foreshadowing_max_age_chapters` |
| 依赖 `chapter_min_chars` 兜底值 | 实得 7000 字下限，远超多数项目预期 | 在 `story_core.yaml` 显式设置 |
| 长章节超 900 秒 | 超时后重试，浪费三次调用成本 | 调大 `META_WRITING_AGENT_TIMEOUT` |
