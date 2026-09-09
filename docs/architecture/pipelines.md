# 编排层：两条链路

系统提供两条生成链路，共享全部下层组件（agent、Story Bible、评分体系、style linter），但编排策略、人工介入点和模型路由都不同。

| | 手动链路 | 自动链路 |
|---|---|---|
| 实现 | [`orchestrator.py`](../../meta_writing/orchestrator.py) | [`auto_runner.py`](../../auto_runner.py) |
| 入口 | `meta-writing generate` | `python auto_runner.py` |
| 要求的 `workflow_mode` | `manual` | `automatic` |
| 粒度 | 一次一章 | `--from N --to M` 连续多章 |
| 状态 | 稳定，推荐用于质量敏感项目 | 见文末说明 |

---

## 1. 工作流模式互斥

每个项目在 `.meta-writing-project.json` 里声明 `workflow_mode`，两条链路都在构造时校验：

```python
# Orchestrator.__init__
if project_metadata and project_metadata.workflow_mode == WORKFLOW_MODE_AUTOMATIC:
    raise ValueError("This project is configured for automatic workflow mode. ...")

# AutoRunner.__init__
if project_metadata and project_metadata.workflow_mode == WORKFLOW_MODE_MANUAL:
    raise ValueError("This project is configured for manual workflow mode. ...")
```

CLI 层还有一道更早的拦截，`_enforce_project_workflow_mode()` 在进入异步流程前就抛 `ClickException`。

**这条互斥的意义**：自动链路会无条件覆写 `chapters/NNN.md` 并直接改 Story Bible。如果一个项目已经进入人工精修阶段，误跑一次 `auto_runner.py --to 20` 就会把二十章手工打磨的文字冲掉。模式标记让这个错误在**第一次 API 调用之前**就被挡住。

切换模式：

```powershell
meta-writing project mode automatic --name my-novel
```

切换前请确认当前章节已提交 git。

---

## 2. 手动链路

### 2.1 三个回调

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

### 2.2 流水线状态机

`PipelineStage` 枚举贯穿全程，`PipelineState` 记录每一步的中间产物：

```
INIT → PLANNING → BRANCH_SELECTION → WRITING
     → [REVIEWING ⇄ REVISING] × ≤5 → HUMAN_REVIEW → COMMITTING → DONE
                                                                  ↘ ERROR
```

`PipelineState` 同时保留了 `editorial_score_history`（用于停滞判断）和 `editorial_review_rounds`（用于落盘留痕）。每次 `generate_chapter()` 开头会清空这两个列表——**Orchestrator 实例可以复用于多章**。

### 2.3 审稿-修订循环

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

**三位 LLM 审稿是顺序 await 的，不是并发的。** 它们之间没有数据依赖，理论上可以 `asyncio.gather`——这是一个尚未实现的优化点，可把审稿墙钟时间压到约三分之一。

**反馈拼接是有条件的**，不是把所有意见一股脑塞给 Writer：

| 来源 | 拼入条件 |
|------|----------|
| `continuity_result.format_feedback()` | 有 critical **或** 未通过 |
| linter 的 `format_feedback_for_writer()` | 仅 ERROR 级（WARNING/INFO 不进） |
| `style_agent_result.format_feedback()` | 有任意 issue |
| `theme_agent_result.format_feedback()` | 有任意 issue |
| 评分卡反馈 | 未过门槛时，且**只列低于地板分的维度** |

有意压低反馈量：修订提示词第 4 条是"最小侵入"，反馈越长，Writer 越容易借修订之机整体重写，反而丢掉原稿里好的部分。

### 2.4 落盘

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

## 3. 自动链路

`AutoRunner` 在手动链路的骨架上，把三个人工环节换成 LLM，并额外增加跨章纠偏。

### 3.1 替换关系

| 手动 | 自动 | 差异 |
|------|------|------|
| 终端选分支 | `BranchSelector` | LLM 给出选择理由，记入运行日志 |
| `approve/edit/reject` | **无** | 无人工闸门，审稿循环退出即落盘 |
| `state_confirmer` + `_apply_state_changes` | `BibleUpdater` | LLM 直接写 YAML，不限于已有字段 |
| 人手写 `learned_rules.md` | `LessonAccumulator` | 从本章问题提取可复用规则并追加 |
| （无） | `CarryoverCorrection` | 见下 |

### 3.2 跨章纠偏

```
第 N 章审稿 → 残留问题 → 序列化到 .auto_runner_correction.json
                              │
第 N+1 章生成 ────────────────┘
    build_generation_guidance(carryover 置于最前, 然后 creator_guidance, learned_rules)
```

把上一章没修好的问题放在创作指导**最前面**，是因为提示词靠前的内容权重更高。这是手动链路不需要的机制——人自己记得上一章的问题。

### 3.3 CLI 参数

```powershell
python auto_runner.py --project <name> --from 1 --to 10
python auto_runner.py --project <name> --to 10 --dry-run   # 只规划选枝，不写不提交
python auto_runner.py --project <name> --to 10 --push      # 每章后 git push
```

`--from` 省略时从 `core.current_chapter + 1` 开始。`--writer-provider` 可覆盖项目配置的写手供应商。

MiniMax 令牌的解析顺序：`MINIMAX_API_KEY` → `ANTHROPIC_AUTH_TOKEN` → 仓库根的 `.env` 文件。缺失则 `sys.exit(1)`。

---

## 4. 当前状态与已知缺口

### 4.1 auto_runner.py 存在未提交的删除

工作区中 `auto_runner.py`、`tests/test_auto_runner.py` 及其设计文档处于已删除但未提交的状态。本文档按仓库 **HEAD** 描述。

若该删除最终落地，以下位置需同步清理：`workspace.py` 的 `WORKFLOW_MODE_AUTOMATIC` 与 `SUPPORTED_WORKFLOW_MODES`、`orchestrator.py` 与 `cli.py` 的模式校验分支、以及本文档与 [`overview.md`](overview.md)。

### 4.2 两条链路的审稿逻辑是重复实现的

阻塞判定、反馈拼接、评分聚合、留痕落盘这四段逻辑在两个文件里各写了一遍，只有 `editorial_scorecard.py` 里的常量和聚合函数是共享的。加一位审稿人或改一次门槛判定，必须两边同步改，否则会出现"手动链路更严、自动链路更松"的静默偏差。

抽出一个共享的 `ReviewLoop` 是当前最有价值的重构，但会同时触碰两条链路，需要两边测试都齐备后再做。

### 4.3 章节摘要失真

见 [`story-bible.md §4`](story-bible.md)——落盘的 `ChapterSummary.summary` 取自规划时的大纲而非成稿，修订幅度大时会失真。手动工作流靠人工补写 `chapter_summaries/NNN.yaml` 兜底。

### 4.4 审稿未并发

见 §2.3。三次独立的 LLM 审稿调用是串行的。
