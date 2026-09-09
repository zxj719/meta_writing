# 迁移到「当前智能体」后端 — 设计文档

> 日期：2026-09-09
> 范围：`meta_writing` 仓库。**不涉及** wolfgame 的 Web 工作台、Worker、ECS 部署。
> 状态：待评审

---

## 1. 目标

把 `meta_writing` 的全部 LLM 调用，从「按供应商硬编码」改为「调用当前环境里的智能体 CLI」。

**改造前**：代码里写死 MiniMax / DeepSeek / Anthropic 三家的 client、端点、模型常量与按角色的路由分派，运行需要三套 API key。

**改造后**：单一 `AgentClient`，子进程调用当前可用的智能体 CLI（Claude Code 或 Codex）。代码里不再出现任何供应商名与模型名，不需要任何模型 API key。

顺带完成两项清理（已确认）：

- 彻底移除自动生成链路 `auto_runner.py` 及其配套的 `automatic` 工作流模式
- 同步更新全部受影响文档

## 2. 非目标

- 不改变流水线结构：规划 → 选枝 → 写作 → 审稿 → 修订 → 人审 → 落盘，全部保留
- 不改变 Story Bible 数据模型（唯一例外见 §5.4）
- 不改变评分体系、style linter、风格档案
- 不触碰 wolfgame 侧任何代码

---

## 3. 关键前置验证

设计基于以下实测结果（2026-09-09，本机 Windows）：

```
$ echo '<prompt>' | claude -p --output-format json --system-prompt '<sys>' --disallowed-tools ...
{"type":"result","subtype":"success","is_error":false,
 "result":"{\"ok\": true, \"n\": 7}",
 "usage":{"input_tokens":11684,"output_tokens":15,
          "cache_creation_input_tokens":7429,"cache_read_input_tokens":0},
 "total_cost_usd":0.133085,
 "modelUsage":{"claude-opus-4-8":{...}},
 "duration_ms":7671}
```

四条结论：

| 结论 | 影响 |
|------|------|
| `result` 字段是干净文本，无代码围栏 | 可直接作为 `LLMResponse.text` |
| `usage` 结构与现有 `TokenUsage.add()` 的键名兼容 | 用量统计零改动 |
| `total_cost_usd` 是真实成本 | 删除硬编码 MiniMax 价格的 `estimated_cost_usd()` |
| **`--bare` 会绕开 OAuth 登录态**，返回 `Not logged in` | 命令中**禁止**使用 `--bare` |

另一条重要观测：一次 trivial 调用消耗 **11,684 input tokens / $0.13**。这是 CLI 每次调用加载 CLAUDE.md、hooks、插件的固定开销。一章最坏约 20 次调用，固定开销将主导成本。**该代价已被明确接受**，不做优化。

---

## 4. 架构

### 4.1 `AgentClient` 契约

```python
class AgentClient:
    def __init__(self, agent: AgentSpec | None = None, timeout: float | None = None) -> None: ...

    async def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        model: str | None = None,        # 忽略：由当前智能体决定
        max_tokens: int | None = None,   # 忽略：由当前智能体决定
        temperature: float = 0.7,        # 语义化，见 §4.4
    ) -> LLMResponse: ...

    usage: TokenUsage
```

**签名与现有 `LLMClient.complete()` 完全一致**。这是本设计的核心取舍：五个 agent 的调用点无需改动，回归风险集中在 `llm.py` 一个文件内。

代价是 `model` 与 `max_tokens` 成为僵尸参数。以显式的 `None` 默认值 + docstring 说明标注，不静默欺骗调用方。

### 4.2 智能体探测

```python
@dataclass(frozen=True)
class AgentSpec:
    kind: str            # "claude" | "codex" | "custom"
    argv: list[str]      # 基础命令
```

探测优先级：

| 顺序 | 来源 | 行为 |
|------|------|------|
| 1 | `META_WRITING_AGENT_CMD` | `shlex.split` 后直接作为基础命令，`kind="custom"` |
| 2 | `META_WRITING_AGENT` | 取值 `claude` / `codex`，未安装则报错 |
| 3 | PATH 探测 | `shutil.which("claude")` → `shutil.which("codex")` |
| 4 | 都没有 | 抛 `AgentNotFoundError`，错误信息列出上述三种配置方式 |

探测在 `AgentClient.__init__` 执行一次并缓存，不每次调用重复探测。

### 4.3 命令构造

**Claude Code**：

```
claude -p
       --output-format json
       --system-prompt <SYSTEM>
       --disallowed-tools Bash Edit Write Read Glob Grep WebFetch WebSearch Task
```

- 不带 `--bare`（会破坏认证，见 §3）
- 不带 `--model`（模型由当前会话决定，这正是「使用当前智能体」的含义）
- 禁用全部工具：这些是纯文本生成调用，agent 不应读写文件，尤其不应擅自改 Story Bible
- 用户消息经 **stdin** 传入，避免超长提示词撞命令行长度上限

**Codex**：

```
codex exec --json --skip-git-repo-check
```

参数取自 wolfgame `server/novelWorkspace.js` 的 `DEFAULT_CODEX_ARGS` 用法。

> ⚠️ **codex 适配器无法在本机验证**——`codex` 不在本机 PATH 上，只存在于 ECS。该适配器按已知用法编写并标注为未验证；若实际输出格式不符，用 `META_WRITING_AGENT_CMD` 兜底。

### 4.4 温度语义化

CLI 没有采样温度旋钮。现有温度分层是有真实作用的（规划 0.8 求发散 / 写作 0.7 / 修订 0.5 求忠实 / 审稿 0.3 求稳定），静默丢弃会让三位审稿人的一致性下降、Planner 的分支趋同——而这正是评分闸门可信度的根基。

改为翻译成 system prompt 末尾追加的一句话：

```python
def _temperature_directive(temperature: float) -> str:
    if temperature <= 0.35:
        return "判断要稳定克制，同一份输入应给出一致结论，不要为了求新而改判。"
    if temperature <= 0.6:
        return "在忠实原文的前提下做必要改动，不要借机重写。"
    return "允许大胆发散；若需要给出多个选项，选项之间必须有明显差异。"
```

**这不等价于采样温度**，只是保住分层意图。文档中如实说明这一点。

### 4.5 响应解析与错误处理

```
subprocess 退出码 != 0        → 重试
stdout 非法 JSON               → 重试
JSON 的 is_error == true       → 重试（把 result 字段作为错误信息）
超时                           → 杀进程后重试
result 为空字符串              → 重试
以上均否                       → 返回 LLMResponse(text=result, usage=..., model=modelUsage 里的名字)
```

保留 `MAX_RETRIES = 3` 与指数退避 `2 ** (attempt + 1)`（2/4/8 秒）。三次耗尽后抛 `AgentInvocationError`，携带最后一次的 stderr 摘要。

超时改为 `META_WRITING_AGENT_TIMEOUT`，默认 **900 秒**（现为 600）。理由：CLI 有固定启动开销，写万字章更慢。

### 4.6 用量与成本

`TokenUsage` 增加 `cost_usd: float` 累加字段，直接累加 CLI 返回的 `total_cost_usd`。

删除 `estimated_cost_usd(model)`——它硬编码 MiniMax 定价，对任何其他后端都不准确。`cli.py` 的成本输出改为读真实累计值。

---

## 5. 改动清单

### 5.1 `meta_writing/llm.py` — 重写

**删除**：`LLMClient`、`DeepSeekClient`、`ClaudeClient`、`build_writer_backend`、`normalize_writer_provider`、`SUPPORTED_WRITER_PROVIDERS`、`WRITER_PROVIDER_*`、全部 `MODEL_*` 常量、`MINIMAX_BASE_URL`、`DEEPSEEK_BASE_URL`、`TokenUsage.estimated_cost_usd`。

**保留**：`LLMResponse`、`TokenUsage`（增加 `cost_usd`）、`MAX_RETRIES`、`RETRY_BACKOFF_BASE`。

**新增**：`AgentSpec`、`detect_agent()`、`AgentClient`、`AgentNotFoundError`、`AgentInvocationError`、`_temperature_directive()`。

模块 docstring 重写——现有那段描述的「推荐路由」本就与手动链路实现不符，整体作废。

### 5.2 `meta_writing/agents/*.py` — 5 行

五个 agent 的构造函数默认值 `model: str = MODEL_SONNET` → `model: str | None = None`，并去掉对 `..llm` 的模型常量 import。方法体一律不动。

### 5.3 `meta_writing/orchestrator.py`

- 删除 writer_provider 路由（约 15 行）与 `api_key` 构造参数
- 删除 `WORKFLOW_MODE_AUTOMATIC` 守卫（约 6 行）
- 五个 agent 共用一个 `AgentClient` 实例

### 5.4 `meta_writing/story_bible/schema.py`

删除 `StoryCore.writer_provider`。

**兼容性**：Pydantic v2 默认 `extra="ignore"`，已实测确认——现存 `novels/rescue-male-lead/story_data/story_core.yaml` 里的 `writer_provider: minimax` 会被忽略而非报错，下次 `loader.save()` 时自然清除。无需迁移脚本。

### 5.5 `meta_writing/workspace.py` — 移除工作流模式

自动链路移除后 `workflow_mode` 只剩一个合法值，成为死重量。**提议整体移除**：

删除 `WORKFLOW_MODE_MANUAL`、`WORKFLOW_MODE_AUTOMATIC`、`SUPPORTED_WORKFLOW_MODES`、`_normalize_workflow_mode()`、`ProjectMetadata.workflow_mode`、`ProjectRecord.workflow_mode`、`set_project_workflow_mode()`、`workflow_mode_for_project_dir()`，以及 `create_project` / `migrate_legacy_root_project` 的 `workflow_mode` 参数。

`ProjectRuntimePaths.auto_runner_log` 与 `PROJECT_COPY_ITEMS` 中的 `auto_runner_log.md` 一并删除。

**兼容性**：`.meta-writing-project.json` 是普通 JSON，`read_project_metadata` 停止读取该键即可，现存文件中残留的 `"workflow_mode": "manual"` 无害。

> 🔍 **本节是评审重点。** 若你希望保留 `workflow_mode` 概念以备将来扩展，改为 `SUPPORTED_WORKFLOW_MODES = ("manual",)` 即可，其余不动。本设计按 YAGNI 选择整体移除。

### 5.6 `meta_writing/cli.py`

- `init`：删除 Writer provider 提问
- `generate`：删除 `_enforce_project_workflow_mode()` 调用与该函数
- `project create` / `project migrate-root`：删除 `--mode` 选项
- `project mode`：**整个子命令删除**
- `project list`：输出去掉 `[<mode>]` 段
- 成本输出：改读 `usage.cost_usd`

### 5.7 `scripts/editorial_pass.py`

删除 `MINIMAX_API_KEY` / `ANTHROPIC_AUTH_TOKEN` 读取与缺失退出逻辑，改用 `AgentClient()`。

### 5.8 `meta_writing/style_linter.py`

`na_zhong_na_zhong` 与 `na_zhong_na_zhong_heavy` 两条规则的 message 里有「MiniMax最高频散文口头禅」。改为不指名供应商的表述（如「高频散文口头禅」）。规则正则与阈值不变。

### 5.9 删除的文件

```
auto_runner.py
tests/test_auto_runner.py
docs/superpowers/plans/2026-04-08-auto-runner-self-correction.md
```

前三者当前已处于「工作区已删除、未提交」状态，本次一并提交。

---

## 6. 测试策略

### 6.1 `tests/test_llm.py` — 重写

全部 mock `asyncio.create_subprocess_exec`，**不真实 spawn 任何进程**。覆盖：

| 用例 | 断言 |
|------|------|
| 探测优先级 | `META_WRITING_AGENT_CMD` > `META_WRITING_AGENT` > PATH |
| 无可用智能体 | 抛 `AgentNotFoundError`，信息含三种配置方式 |
| claude 命令构造 | 含 `-p --output-format json`；**不含 `--bare`**；**不含 `--model`**；工具已禁用 |
| 提示词传递 | 用户消息经 stdin，system 经 `--system-prompt` |
| 正常响应解析 | `result` → `text`；`usage` → `TokenUsage`；`total_cost_usd` 累加 |
| `is_error: true` | 触发重试 |
| 非法 JSON | 触发重试 |
| 重试耗尽 | 抛 `AgentInvocationError` |
| 温度语义化 | 0.3 / 0.5 / 0.8 分别落到三段不同指令 |

### 6.2 `tests/test_workspace.py`

- 删除 `from auto_runner import resolve_runner_project_dir`（**当前正是它让整个测试套件 collection error**）
- 删除全部 `WORKFLOW_MODE_AUTOMATIC` 相关用例（4 处）与 `project mode` 命令用例
- 删除 `auto_runner_log` 路径断言

### 6.3 `tests/test_orchestrator.py`

- 删除 `test_rejects_automatic_workspace_project`
- mock 目标由 `LLMClient` 改为 `AgentClient`

### 6.4 其余测试

`test_continuity.py` / `test_planner.py` / `test_style_agent.py` / `test_theme.py` / `test_writer.py`：mock 目标改名，去掉模型名断言。

`tests/conftest.py`：`sample_core` 删除 `writer_provider="minimax"`。

### 6.5 验收标准

```powershell
python -m pytest -q          # 必须全绿，且不再有 collection error
rg -in "minimax|deepseek|anthropic|claude-opus|claude-sonnet" meta_writing/ scripts/ tests/
                             # 除 AgentSpec 里的 "claude"/"codex" 命令名外，应无匹配
```

外加一次**真实**冒烟：对一个临时项目跑通 `meta-writing generate` 的规划阶段，确认子进程调用链可用。

---

## 7. 文档改动

同一变更内完成，避免文档有任何一刻是错的。

| 文档 | 处理 |
|------|------|
| `docs/architecture/model-routing.md` | **重写**为 `agent-backend.md`（`git mv` 保历史）：探测、命令构造、温度语义化、错误处理、固定开销 |
| `docs/architecture/overview.md` | 四层架构图去掉 auto_runner；§4「两条链路」整节删除；§7 稳健性更新 |
| `docs/architecture/pipelines.md` | **大幅重写**：只剩一条链路，删除工作流模式互斥与自动链路全部内容 |
| `docs/architecture/agents.md` | 删除「自动链路专属 agent」一节；扩展一节改为单链路 |
| `docs/reference/configuration.md` | 凭据表 → 智能体探测变量表；删除写手供应商与三级回退；更新「已知陷阱」 |
| `docs/reference/cli.md` | 删除 `project mode`、`--mode`、`auto_runner.py` 一节；`init` 去掉 provider 提问 |
| `docs/reference/story-bible-schema.md` | 删除 `writer_provider` |
| `docs/reference/style-rules.md` | 同步 §5.8 的 message 改动 |
| `docs/guides/getting-started.md` | 密钥配置 → 智能体准备 |
| `docs/guides/multi-project-workspace.md` | 删除 manual/automatic 模式一节 |
| `docs/guides/new-novel-quickstart.md` | 删除 MiniMax auth 一节 |
| `docs/operations/editorial-scorecard-maintenance.md` | §8/§9「两条链路」合并为一条；修复指向 auto_runner.py 的死链 |
| `docs/decisions/README.md` | 标注 auto_runner 相关计划为「已移除」 |
| `docs/README.md` | 更新 model-routing → agent-backend 的链接 |
| `README.md` | 「模型供应商」一节 → 「运行前提：一个可用的智能体 CLI」；删除两种工作流表 |

---

## 8. 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| codex 适配器未经验证 | ECS 上可能跑不通 | 标注未验证；`META_WRITING_AGENT_CMD` 兜底；不阻塞本机使用 |
| 每章成本显著上升 | 固定开销 ~11.7K token/次 | **已明确接受**，文档如实记录 |
| 失去采样温度 | 审稿一致性、分支多样性下降 | 语义化缓解；文档说明不等价 |
| 移除 workflow_mode 是单向的 | 将来若想恢复自动链路要重建 | 本节已在 §5.5 标为评审重点 |
| 长文生成超时 | 章节写作可能超 900s | 超时可经环境变量调大；重试保留 |
| 嵌套智能体调用 | 若从 Claude Code 会话里跑 `generate`，会 spawn 另一个 claude 进程 | 可行但更慢更贵；文档提示直接在普通终端运行 |

---

## 9. 实施顺序

1. `llm.py` 重写 + `test_llm.py` 重写（TDD：先测后写）
2. 五个 agent 的构造函数默认值
3. `orchestrator.py` 去供应商路由 + 去模式守卫
4. `workspace.py` / `cli.py` 去工作流模式
5. `schema.py` / `editorial_pass.py` / `style_linter.py` 收尾
6. 删除 auto_runner 三件套
7. 测试全绿 + 真实冒烟
8. 文档同步
9. 单次提交

---

## 10. 待评审确认

1. **§5.5**：`workflow_mode` 整体移除，还是保留字段只留 `manual` 一个值？（本设计选前者）
2. **§4.3**：Claude Code 调用是否要禁用全部工具？（本设计选禁用；若你希望 agent 能自己读 Story Bible 文件，则应放开 Read/Glob/Grep）
3. **§4.4**：温度语义化的三段措辞是否合适？
