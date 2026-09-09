# 模型路由

> 代码位置：[`meta_writing/llm.py`](../../meta_writing/llm.py)

系统支持三家供应商，通过三个 client 类接入。**两条编排链路的路由策略完全不同**——这是阅读代码时最容易踩的一个坑。

---

## 1. 三个 client

三者暴露同一个 `complete()` 接口，可互相替换：

```python
async def complete(system, messages, model, max_tokens=8192, temperature=0.7) -> LLMResponse
```

| Client | SDK | 端点 | 凭据 |
|--------|-----|------|------|
| `LLMClient` | `anthropic` | `https://api.minimaxi.com/anthropic` | `MINIMAX_API_KEY` → `ANTHROPIC_AUTH_TOKEN` |
| `DeepSeekClient` | `openai` | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` |
| `ClaudeClient` | `anthropic` | `https://api.anthropic.com` | `ANTHROPIC_API_KEY` |

`LLMClient` 的命名有历史包袱：它**不是**通用基类，而是专指 MiniMax 客户端。MiniMax 提供 Anthropic 兼容端点，所以它用 `anthropic` SDK 但指向 MiniMax 的 base URL。

### 各自的适配细节

**`LLMClient`（MiniMax）**
- 温度被钳制到 `(0.0, 1.0]`：`max(0.01, min(1.0, temperature))`，MiniMax 不接受 0
- 强制走流式（`messages.stream`）并消费完再取最终消息——长文生成时保活连接
- 超时 600 秒，连接超时 30 秒

**`DeepSeekClient`**
- 把 Anthropic 风格的 `system` + `messages` 转成 OpenAI 风格（system 作为首条 message）
- `max_tokens` 硬性截到 8192——DeepSeek 的上限
- 非流式

**`ClaudeClient`**
- 温度钳到 `[0.0, 1.0]`（允许 0）
- 流式，超时同 MiniMax

### 模型常量

```python
MODEL_OPUS   = "MiniMax-M2.7"      # ← 注意：不是 Claude Opus
MODEL_SONNET = "MiniMax-M2.7"      # ← 与上面同值
MODEL_DEEPSEEK_CHAT     = "deepseek-chat"
MODEL_DEEPSEEK_REASONER = "deepseek-reasoner"   # 未被使用
MODEL_CLAUDE_OPUS   = "claude-opus-4-6"
MODEL_CLAUDE_SONNET = "claude-sonnet-4-6"
```

`MODEL_OPUS` 与 `MODEL_SONNET` 是同一个字符串。它们保留了早期用 Claude 时的命名，现在都指向 MiniMax-M2.7。代码里区分 `planner_model=MODEL_OPUS` / `continuity_model=MODEL_SONNET` 在手动链路里**没有实际差别**。

---

## 2. 手动链路的路由

[`Orchestrator.__init__`](../../meta_writing/orchestrator.py) 只构造一个 client：

```python
self.llm = LLMClient(api_key=api_key)          # MiniMax

self.planner       = PlannerAgent(self.llm,  model=planner_model)     # MODEL_OPUS   → MiniMax-M2.7
self.writer        = WriterAgent(writer_llm, model=resolved_writer_model)
self.continuity    = ContinuityAgent(self.llm, model=continuity_model) # MODEL_SONNET → MiniMax-M2.7
self.style_agent   = StyleAgent(self.llm,     model=continuity_model)
self.theme_agent   = ThemeAgent(self.llm,     model=continuity_model)
```

**除 Writer 外，全部 agent 都跑在 MiniMax 上。** Writer 是唯一可切换的：

```python
resolved_writer_provider = writer_provider or (core.writer_provider if core else "minimax")
writer_llm, auto_writer_model = build_writer_backend(resolved_writer_provider, minimax_api_key=api_key)
if resolved_writer_provider == "minimax":
    writer_llm = self.llm          # 复用同一个 MiniMax client，避免重复构造
```

即：手动链路只需要 `MINIMAX_API_KEY`（写手切到 DeepSeek 时另需 `DEEPSEEK_API_KEY`）。不设 `ANTHROPIC_API_KEY` 也能完整运行。

> **文档与实现的偏差**：[`llm.py`](../../meta_writing/llm.py) 顶部的模块 docstring 描述了一套"推荐路由"（Planner→Claude Opus、Writer→DeepSeek、ThemeAgent→Claude Opus……）。**那描述的是自动链路的路由，不是手动链路的。** 手动链路从未实现多供应商路由。

---

## 3. 自动链路的路由

[`AutoRunner.__init__`](../../auto_runner.py) 实现了真正的三供应商路由，按角色分派：

| 角色 | 目标 client |
|------|------------|
| Planner / ContinuityAgent / ThemeAgent / BranchSelector | `claude_llm`（编辑角色） |
| Writer | 按 `writer_provider` 决定 |
| StyleAgent | `minimax_llm`（快且便宜） |
| BibleUpdater / LessonAccumulator | `deepseek_llm`（结构化 JSON 可靠） |

角色分派的依据：**编辑判断力用最强的模型，中文散文用中文原生模型，结构化抽取用 JSON 最稳的模型，高频轻量检查用最便宜的模型。**

### 三级回退

`claude_llm` 的解析取决于环境里有哪些凭据：

```
ANTHROPIC_API_KEY 存在
  └─ claude_llm = ClaudeClient，planner=claude-opus-4-6，review_strong=opus，review_fast=sonnet
     └─ 且 DEEPSEEK_API_KEY 缺失 → deepseek_llm 降级为 minimax_llm

ANTHROPIC_API_KEY 缺失、DEEPSEEK_API_KEY 存在
  └─ claude_llm = deepseek_llm，全部编辑角色 → deepseek-chat        [WARNING]

两者都缺失
  └─ claude_llm = deepseek_llm = minimax_llm，全部角色 → MiniMax     [WARNING]
```

两次降级都会打 `logger.warning`。**运行自动链路时请检查日志首几行**——静默降级到全 MiniMax 会显著改变审稿严格度，而输出格式完全不变，很难从结果反推。

写手 client 的最终归属：

```python
writer_llm, writer_model = build_writer_backend(self.writer_provider, minimax_api_key=api_key)
if self.writer_provider == "minimax":
    writer_llm = minimax_llm
else:
    writer_llm = deepseek_llm     # 注意：可能已被降级为 minimax_llm
```

第二个分支有一个后果：若选了 `deepseek` 写手但 `DEEPSEEK_API_KEY` 缺失、`ANTHROPIC_API_KEY` 存在，`deepseek_llm` 已被降级成 `minimax_llm`，于是**写手实际跑在 MiniMax 上，但 `writer_model` 仍是 `"deepseek-chat"`**。这个组合会导致 API 报错。要用 DeepSeek 写手，务必设 `DEEPSEEK_API_KEY`。

---

## 4. 写手供应商

```python
SUPPORTED_WRITER_PROVIDERS = ("deepseek", "minimax")
```

配置优先级：CLI `--writer-provider` > `StoryCore.writer_provider`（`story_data/story_core.yaml`）> 默认值。

**两处默认值不一致**，需要留意：

| 位置 | 默认 |
|------|------|
| `StoryCore.writer_provider` schema 默认 | `"minimax"` |
| `Orchestrator` 无 core 时的兜底 | `"minimax"` |
| `normalize_writer_provider()` 的 `fallback` | `"deepseek"` |

`normalize_writer_provider` 只在传入值**不在支持列表里**时才用 fallback。正常路径下 `"minimax"` 会原样通过，走不到 deepseek 分支。只有拼错供应商名（如 `"minmax"`）时才会静默变成 DeepSeek——**不会报错，只会换供应商**。

---

## 5. 重试与用量

`MAX_RETRIES = 3`，指数退避 `2 ** (attempt + 1)` 秒（2 / 4 / 8）。

MiniMax 与 Claude client 的重试条件：

```python
except (RateLimitError, APIConnectionError):  重试
except APIStatusError as e:
    if e.status_code >= 500:  重试
    else:                     raise      # 4xx 立即抛出
```

4xx 不重试是对的——认证错误、参数错误重试三次只是浪费 24 秒。DeepSeek client 的实现较粗，`except Exception` 捕获全部异常并重试，包括 4xx。

每个 client 各自维护一个 `TokenUsage`。自动链路持有三个 client 的引用用于分别统计；手动链路只报告 `orch.llm.usage`——**当写手跑在 DeepSeek 上时，CLI 报告的 token 用量不含写作部分**，会显著低估。

`estimated_cost_usd()` 硬编码了 MiniMax 的价格（输入 $1/M、输出 $5/M），对其他供应商不准确。
