# 编排层

> 代码位置：[`meta_writing/orchestrator.py`](../../meta_writing/orchestrator.py)
> 入口：`meta-writing generate`

系统只有一条生成链路：人负责选枝、验收与状态确认，机器负责规划、写作、审稿与修订。

> **历史说明**：早期还有一条全自动链路 `auto_runner.py`（LLM 选枝、无人工闸门、LLM 直接写回 Story Bible），以及配套的 `manual` / `automatic` 工作流模式互斥。二者已于 2026-09-09 随智能体后端迁移一并移除。归档见 [`../decisions/README.md`](../decisions/README.md)。

---

## 1. 三个回调

`Orchestrator.generate_chapter()` 把全部人工决策点抽成三个异步回调，由调用方提供：

```python
BranchSelector       = Callable[[list[PlotBranch]], Awaitable[int]]
HumanReviewer        = Callable[[str, ContinuityResult | None], Awaitable[tuple[str, str]]]
StateChangeConfirmer = Callable[[list[dict]], Awaitable[bool]]
```

| 回调 | 时机 | 返回 |
|------|------|------|
| `branch_selector` | Planner 出分支后 | 选中的分支序号 |
| `human_reviewer` | 审稿循环结束后 | `("approve"\|"edit"\|"reject", notes)` |
| `state_confirmer` | 写盘前，有状态变更时 | 是否写回 Story Bible |

[`cli.py`](../../meta_writing/cli.py) 用 Rich 的表格与 Prompt 实现了这三个回调。**这个抽象让编排层与终端 UI 解耦**——换一套 UI（或换成全自动策略）只需换回调实现，编排逻辑一行不用改。

`human_reviewer` 的三种动作：

- `approve` → 用当前正文继续
- `edit` → **用 `notes` 整体替换正文**（不是打补丁）
- `reject` → 抛 `RuntimeError`，流程终止，不落盘

---

## 2. 构造与依赖注入

```python
Orchestrator(project_dir, llm: AgentClient | None = None)
```

`llm` 省略时构造一个 `AgentClient()`，它在初始化时就会探测智能体 CLI（找不到即抛 `AgentNotFoundError`）。显式传入可跳过探测——测试走的就是这条路径（[`tests/helpers.py`](../../tests/helpers.py)），这样测试不依赖运行机器上装没装智能体。

五个 agent 共用同一个 `AgentClient` 实例，因此 token 与成本统计是全流程汇总的。

---

## 3. 流水线状态机

`PipelineStage` 枚举贯穿全程，`PipelineState` 记录每一步的中间产物：

```
INIT → PLANNING → BRANCH_SELECTION → WRITING
     → [REVIEWING ⇄ REVISING] × ≤5 → HUMAN_REVIEW → COMMITTING → DONE
                                                                  ↘ ERROR
```

`PipelineState` 同时保留了 `editorial_score_history`（用于停滞判断）和 `editorial_review_rounds`（用于落盘留痕）。每次 `generate_chapter()` 开头会清空这两个列表——**Orchestrator 实例可以复用于多章**。

---

## 4. 审稿-修订循环

```python
for iteration in range(MAX_REVISION_ITERATIONS):   # 5
    style_issues = self.style_linter.check(chapter_text)          # 确定性，零成本
    continuity_result   = await self.continuity.review(...)       # ┐
    style_agent_result  = await self.style_agent.review(...)      # ├ 各出一张评分卡
    theme_agent_result  = await self.theme_agent.review_chapter(...)  # ┘

    editorial_score = aggregate_editorial_scorecards([...三张卡...])

    review_passed = (
        continuity_result.passed
        and not continuity_result.has_critical
        and not has_style_errors                  # linter 的 ERROR
        and not style_agent_result.has_errors     # StyleAgent 的 error
        and not theme_agent_result.has_critical
        and editorial_score.passes_threshold(8.0) # 综合 ≥8.0 且无单维 <7.0
    )
    if review_passed:              break  # → "passed"
    if editorial_progress_stalled(history): break  # → "stalled_below_threshold"
    if iteration == 4:             break  # → "max_revisions_reached"

    chapter_text = (await self.writer.revise(chapter_text, feedback, ...)).chapter_text
```

**三位 LLM 审稿是顺序 await 的，不是并发的。** 它们之间没有数据依赖，理论上可以 `asyncio.gather`——这是一个尚未实现的优化点。在智能体 CLI 后端下收益比过去更大：每次调用都有约 11.7K token 的固定开销与可观的启动延迟，并发能把审稿墙钟时间压到约三分之一。

**反馈拼接是有条件的**，不是把所有意见一股脑塞给 Writer：

| 来源 | 拼入条件 |
|------|----------|
| `continuity_result.format_feedback()` | 有 critical **或** 未通过 |
| linter 的 `format_feedback_for_writer()` | 仅 ERROR 级（WARNING/INFO 不进） |
| `style_agent_result.format_feedback()` | 有任意 issue |
| `theme_agent_result.format_feedback()` | 有任意 issue |
| 评分卡反馈 | 未过门槛时，且**只列低于地板分的维度** |

有意压低反馈量：修订提示词第 4 条是"最小侵入"，反馈越长，Writer 越容易借修订之机整体重写，反而丢掉原稿里好的部分。

---

## 5. 落盘

无论循环以哪种结局退出，都会写审稿留痕：

```
editorial_reviews/NNN.md     人读：每轮的综合分、是否达标、阻塞项、五维分
editorial_reviews/NNN.json   机读：同样内容的结构化版本
```

`final_decision` 三种取值：`passed` / `stalled_below_threshold` / `max_revisions_reached`。**后两者意味着这一章是带着已知问题落盘的**，人工复核时应优先看这些章。

随后 `_commit_chapter()`：

```
写 chapters/NNN.md
  → 有状态变更？→ state_confirmer 确认 → _apply_state_changes()
  → core.current_chapter = N
  → chapter_summaries[N] = ChapterSummary(summary=branch.outline[:200], ...)
  → loader.save(bible)          整本 Story Bible 写回
  → git add story_data/ chapters/ && git commit
```

`_git_commit()` 用 `try/except subprocess.CalledProcessError: pass` 包住——**git 失败是静默的**。不在 git 仓库里、没配 user.email、没有变更可提交，都不会中断流程，但也不会有任何提示。生成完请自行 `git log -1` 确认。

---

## 6. 已知缺口

### 6.1 章节摘要失真

落盘的 `ChapterSummary.summary` 取自规划时的大纲前 200 字而非成稿，修订幅度大时会失真。手动工作流靠人工补写 `chapter_summaries/NNN.yaml` 兜底。详见 [`story-bible.md §4`](story-bible.md)。

### 6.2 审稿未并发

见 §4。三次独立的智能体调用是串行的，在 CLI 后端下代价比过去更明显。

### 6.3 git 提交静默失败

见 §5。
