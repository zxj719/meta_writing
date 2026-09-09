# 智能体后端

> 代码位置：[`meta_writing/llm.py`](../../meta_writing/llm.py)

系统不直接调用任何模型供应商的 HTTP API。全部生成与审稿都通过**子进程调用当前环境里的智能体 CLI**（Claude Code 或 Codex）完成。

这带来三个直接后果：

- **不需要任何模型供应商的 API key** —— 没有 MiniMax / DeepSeek / Anthropic 的凭据配置
- **模型由当前智能体会话决定** —— 代码不指定模型，用什么就是什么
- **每次调用有固定开销** —— CLI 启动、上下文加载，约 11.7K input token/次

---

## 1. 智能体探测

```python
@dataclass(frozen=True)
class AgentSpec:
    kind: str            # "claude" | "codex" | "custom"
    argv: tuple[str, ...]
```

`detect_agent()` 按三档优先级解析：

| 顺序 | 来源 | 行为 |
|------|------|------|
| 1 | `META_WRITING_AGENT_CMD` | `shlex.split` 后直接作为基础命令，`kind="custom"` |
| 2 | `META_WRITING_AGENT` | 取值 `claude` / `codex`；值非法或命令不在 PATH 上则报错 |
| 3 | PATH 探测 | `claude` 优先，其次 `codex` |
| 4 | 都没有 | 抛 `AgentNotFoundError`，错误信息列出上述三种配置方式 |

探测在 `AgentClient.__init__` 执行一次并缓存。

`AgentClient` 也接受显式的 `agent=AgentSpec(...)`，跳过探测——测试用的就是这条路径（见 [`tests/helpers.py`](../../tests/helpers.py)），这样测试不依赖运行机器上装没装智能体。

---

## 2. 命令构造

### Claude Code

```
claude -p
       --output-format json
       --system-prompt <SYSTEM>
       --disallowed-tools Bash Edit Write Read Glob Grep WebFetch WebSearch Task
```

用户消息经 **stdin** 传入，避免超长提示词撞命令行长度上限。

三个刻意的选择：

| 决定 | 原因 |
|------|------|
| **不带 `--bare`** | 它把认证限制为 `ANTHROPIC_API_KEY`，绕开 OAuth 登录态。实测直接返回 `Not logged in · Please run /login` |
| **不带 `--model`** | 模型由当前会话决定——这正是「使用当前智能体」的含义 |
| **禁用全部工具** | 这些是纯文本生成调用；智能体不应读写文件，尤其不应擅自改 Story Bible |

### Codex

```
codex exec --skip-git-repo-check
```

`codex exec` **没有 `--system-prompt` 参数**，因此 system 文本会并进 stdin：

```
<system prompt>

---

<user prompt>
```

也**不用** `--full-auto`——那会授予工具权限，与「禁用全部工具」的取向相反。

`kind="custom"` 按 codex 方式处理（system 并进 stdin），因为无法预知自定义命令的参数。

> ⚠️ **codex 适配器未经实测**。`codex` 不在开发机的 PATH 上，只存在于 ECS。该适配器按已知用法编写；若实际行为不符，用 `META_WRITING_AGENT_CMD` 兜底。

---

## 3. 必须在空目录中运行

**子进程的 `cwd` 被强制设为系统临时目录下的一个空目录**（`neutral_cwd()`），而不是仓库目录。

这不是洁癖，是必需的：智能体 CLI 会从 cwd 向上自动发现 `CLAUDE.md` 等项目上下文。在仓库内运行时，它会把自己当成「本项目的助手」，在输出前加旁白。实测对比同一个调用：

| cwd | 返回 | 成本 |
|-----|------|------|
| 仓库目录 | `I need to follow the project's JSON generator instruction.\n\n{"ok": true}` | $0.147 |
| 空目录 | `{"ok": true}` | $0.063 |

对审稿调用，这段旁白只是噪声——JSON 提取器会找到外层花括号绕过它。但对**写作调用，正文即返回文本**，旁白会被原样写进 `chapters/NNN.md`。

顺带的好处是成本降了一半以上。

---

## 4. 温度语义化

智能体 CLI 没有采样温度旋钮。原有的温度分层是有真实作用的：

| 角色 | 原温度 | 意图 |
|------|--------|------|
| Planner | 0.8 | 分支要发散 |
| Writer 写作 / 扩写 | 0.7 | 正常创作 |
| Writer 修订 | 0.5 | 忠实原文 |
| 三位审稿人 | 0.3 | 判断要稳定 |

静默丢弃会让审稿一致性下降、Planner 分支趋同——而这正是评分闸门可信度的根基。因此改为翻译成 system prompt 末尾追加的一句话：

```python
temperature <= 0.35  → "判断要稳定克制，同一份输入应给出一致结论，不要为了求新而改判。"
temperature <= 0.6   → "在忠实原文的前提下做必要改动，不要借机重写。"
else                 → "允许大胆发散；若需要给出多个选项，选项之间必须有明显差异。"
```

**这不等价于采样温度**，只是保住分层意图。agent 层的调用点仍照原样传 `temperature=0.3` 等值，无需改动。

---

## 5. 响应解析

### Claude（`--output-format json`）

```json
{
  "is_error": false,
  "result": "<生成的文本>",
  "usage": {"input_tokens": 11684, "output_tokens": 15},
  "total_cost_usd": 0.133085,
  "modelUsage": {"claude-opus-4-8": {}}
}
```

| 字段 | 去向 |
|------|------|
| `result` | `LLMResponse.text` |
| `usage` | 累加进 `TokenUsage` |
| `total_cost_usd` | 累加进 `TokenUsage.cost_usd` —— **真实成本，不是估算** |
| `modelUsage` 的首个键 | `LLMResponse.model`（智能体回报的运行时元数据） |

### Codex / custom

取 stdout 纯文本作为 `LLMResponse.text`，**不采集用量**（`TokenUsage` 保持 0）。这是有意的：与其猜测事件流的结构，不如取最可靠的东西。

---

## 6. 重试与超时

`MAX_RETRIES = 3`，指数退避 `2 ** (attempt + 1)` 秒（2 / 4 / 8）。

重试条件：

| 情况 | 处理 |
|------|------|
| 子进程退出码非 0 | 重试，错误信息带 stderr 前 500 字 |
| stdout 不是合法 JSON（claude） | 重试 |
| JSON 的 `is_error: true` | 重试，错误信息取 `result` |
| 结果为空字符串 | 重试 |
| 超时 | 杀进程后重试 |

三次耗尽抛 `AgentInvocationError`，携带最后一次的错误信息。

超时默认 **900 秒**，经 `META_WRITING_AGENT_TIMEOUT` 覆盖。比 HTTP 时代的 600 秒宽——CLI 有固定启动开销，写万字章更慢。

---

## 7. 用量与成本

每个 `AgentClient` 维护一个 `TokenUsage`，累加 token 与**真实成本**。旧的 `estimated_cost_usd()`（硬编码 MiniMax 定价）已删除。

`meta-writing generate` 结束时打印的是实际花费，不再是估算。

---

## 8. 成本特征

这是从 HTTP API 换到 CLI 最大的经济性变化：**每次调用约 11.7K input token 的固定开销**，与提示词长短基本无关。

一章的调用次数：

```
1 次规划 + 1 次写作（不足字数则 +1 次扩写）
+ 每轮审稿 3 次 × 最多 5 轮
+ 每轮修订 1 次 × 最多 4 次
≈ 最坏 20 余次
```

固定开销会主导总成本。这一代价在设计评审时已被明确接受，不做优化。若要压低，可选项是降低 `MAX_REVISION_ITERATIONS`，或把三位审稿人合并为单次调用——但后者会牺牲「三位审稿人相互独立、避免锚定」的设计。

---

## 9. 嵌套调用

若从一个 Claude Code 会话里运行 `meta-writing generate`，Python 会再 spawn 一个 `claude` 进程——这是嵌套智能体调用。能跑通，但更慢更贵。

建议在普通终端里直接运行。

---

## 10. 相关文档

| 主题 | 文档 |
|------|------|
| 环境变量与配置项 | [`../reference/configuration.md`](../reference/configuration.md) |
| 五个 agent 如何消费这个后端 | [`agents.md`](agents.md) |
| 总体设计 | [`overview.md`](overview.md) |
