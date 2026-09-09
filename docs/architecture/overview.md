# 系统总体设计

> 适用范围：`meta_writing` 引擎本体
> 目标读者：需要理解整体结构、或准备改动核心链路的人

`meta_writing` 是一个**本地优先（local-first）的中文长篇小说生成引擎**。它不依赖任何 Web 服务、部署环境或外部编排器：一个 Python 包、一个 CLI、一棵磁盘上的文件树，就是系统的全部。所有状态都是 git 可追踪的纯文本（YAML + Markdown）。

---

## 1. 系统要解决的问题

长篇小说的 AI 生成，真正的难点不是"写出一章能读的文字"，而是三件事：

| 问题 | 表现 | 本系统的应对 |
|------|------|--------------|
| **状态漂移** | 写到第 30 章，角色的伤势/位置/知识状态与第 12 章矛盾 | Story Bible：结构化、可校验、每章更新的显式状态层 |
| **上下文溢出** | 故事状态迟早超过模型上下文窗口 | Compressor：三级降级压缩，把状态压进固定 token 预算 |
| **质量塌陷** | 模型写得越来越像模型：模板句式、总结腔、空洞的"有力感" | 双层质量闸门：确定性 linter + 三位 LLM 审稿 + 五维评分卡 |

围绕这三点，系统被切成四层。

---

## 2. 四层架构

```
┌──────────────────────────────────────────────────────────────┐
│  编排层 Orchestration                                         │
│  orchestrator.py（手动）  /  auto_runner.py（自动）            │
│  规划 → 选枝 → 写作 → 审稿 → 修订 → 人审 → 落盘 → git commit    │
└───────────────┬──────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────┐
│  智能体层 Agents                                              │
│  Planner  Writer  ┃  Continuity  Style  Theme                 │
│  （生成侧）        ┃  （审稿侧，各自产出一张评分卡）             │
└───────────────┬──────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────┐
│  质量层 Quality                                               │
│  style_linter.py（确定性正则）                                 │
│  editorial_scorecard.py（五维加权 + 硬门槛 + 停滞判断）         │
│  negative_examples.py（bad→good 反例注入）                     │
│  prompt_profiles.py（项目风格档案）                            │
└───────────────┬──────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────┐
│  状态层 State                                                 │
│  story_bible/（schema 校验 · YAML 读写 · 上下文压缩）           │
│  workspace.py（多项目隔离 · 工作流模式）                        │
│  vector_store/（可选：章节语义检索）                            │
└──────────────────────────────────────────────────────────────┘
```

四层之间是**单向依赖**：编排层调用智能体层，智能体层消费质量层与状态层，状态层不知道上面任何一层的存在。这条约束是刻意的——它让 Story Bible 可以被 CLI、被自动循环、被任何外部工具（包括不属于本仓库的编辑器）独立读写。

---

## 3. 一章的生命周期

以手动链路（[`orchestrator.py`](../../meta_writing/orchestrator.py)）为准：

```
  load_bible()                     从 story_data/ 读出完整 StoryBible
        │
        ▼
  chapter_number = core.current_chapter + 1
        │
        ▼
  detect_prompt_profile()          按创作指导文本选风格档案
        │
        ▼
  compressor.compress()            压成 ≤15K token 的上下文
        │
        ▼
  Planner.plan()                   产出 2-3 条剧情分支（JSON）
        │
        ▼
  branch_selector()                人选 / 自动选一条
        │
        ▼
  compressor.compress(             按选中分支的角色重新压缩
      active_character_names=…)
        │
        ▼
  Writer.write_with_expansion()    写正文；不足字数则自动扩写
        │
        ▼
  ┌─── 审稿-修订循环（最多 5 轮）──────────────────────┐
  │                                                    │
  │   StyleLinter.check()          确定性正则，零成本   │
  │   Continuity.review()  ─┐                          │
  │   Style.review()        ├─ 各返回一张五维评分卡      │
  │   Theme.review_chapter()┘                          │
  │            │                                       │
  │            ▼                                       │
  │   aggregate_editorial_scorecards()                 │
  │            │                                       │
  │            ▼                                       │
  │   通过？ ── 是 ──▶ 跳出                             │
  │     │                                              │
  │     否                                             │
  │     ├─ 进步停滞？ ──▶ stalled_below_threshold 跳出  │
  │     ├─ 到第 5 轮？ ──▶ max_revisions_reached 跳出   │
  │     └─ Writer.revise(feedback) ──▶ 回到循环开头     │
  └────────────────────────────────────────────────────┘
        │
        ▼
  写 editorial_reviews/NNN.md + .json     审稿留痕
        │
        ▼
  human_reviewer()                 approve / edit / reject
        │
        ▼
  _commit_chapter()                写 chapters/NNN.md
                                   确认并应用角色状态变更
                                   写回 story_data/
                                   git add + commit
```

**关键设计点**：压缩发生两次。第一次在规划前（不知道谁会出场，按最近三章推断活跃角色），第二次在写作前（分支已选定，角色名已知，可以精确取舍）。这让 Planner 拿到的是宽而浅的上下文，Writer 拿到的是窄而深的上下文。

---

## 4. 两条链路

系统有两条编排链路，**共享全部下层组件，但编排策略与模型路由完全不同**。

| | 手动链路 | 自动链路 |
|---|---|---|
| 入口 | `meta-writing generate` | `python auto_runner.py` |
| 实现 | [`orchestrator.py`](../../meta_writing/orchestrator.py) | [`auto_runner.py`](../../auto_runner.py) |
| 分支选择 | 人在终端选 | `BranchSelector` LLM 选 |
| 章节验收 | 人 approve/edit/reject | 无人工闸门 |
| 状态更新 | `ContinuityAgent` 检出变更 + 人确认 | `BibleUpdater` LLM 直接写回 |
| 经验沉淀 | 人手写 `learned_rules.md` | `LessonAccumulator` 自动追加 |
| 跨章纠偏 | 无 | `CarryoverCorrection` 把上一章问题带进下一章 |
| 模型路由 | 全部走 MiniMax | Anthropic → DeepSeek → MiniMax 三级回退 |
| git | commit | commit（`--push` 时另外 push） |

两条链路**互斥**，由项目元数据 `.meta-writing-project.json` 的 `workflow_mode` 强制：

- `manual` 项目下运行 `auto_runner.py` → `ValueError`
- `automatic` 项目下运行 `meta-writing generate` → `ClickException`

这条互斥不是防呆装饰，而是防止自动循环覆写人工精修过的章节。详见 [`pipelines.md`](pipelines.md)。

> **当前状态提示**：工作区存在一处尚未提交的 `auto_runner.py` 删除。若该删除最终落地，自动链路即被移除，`workspace.py` / `orchestrator.py` / `cli.py` 中的 `WORKFLOW_MODE_AUTOMATIC` 分支应同步清理。本文档按仓库 HEAD 的状态描述。

---

## 5. 磁盘布局即接口

系统没有数据库、没有服务端、没有内部 API。**文件树本身就是模块之间的契约**：

```
<workspace root>/
├── novels/                        项目库
│   └── <project>/
│       ├── .meta-writing-project.json    项目名 + workflow_mode
│       ├── creator_guidance.md           长期创作指导（人写）
│       ├── learned_rules.md              累积的风格/连续性规则
│       ├── chapters/
│       │   └── NNN.md                    章节正文
│       ├── story_data/                   ← Story Bible
│       │   ├── story_core.yaml
│       │   ├── characters/*.yaml
│       │   ├── timeline.yaml
│       │   ├── world_rules.yaml
│       │   ├── foreshadowing.yaml
│       │   ├── pacing.yaml
│       │   └── chapter_summaries/NNN.yaml
│       └── editorial_reviews/
│           ├── NNN.md                    人读的审稿记录
│           └── NNN.json                  机读的审稿记录
└── .meta-writing/
    └── workspace.json                    当前激活项目
```

这个选择带来三个直接后果：

1. **可 diff、可 review、可回滚**——每一章连同它引发的状态变更一起进 git，`git show` 就能看到"这一章改了谁的情绪状态"。
2. **可被任意工具消费**——外部编辑器、脚本、乃至另一个仓库的 Web 界面，只要能读写文件就能接入，不需要本系统提供 API。
3. **章节与状态必须一起提交**——只有正文没有状态更新的提交，视为不完整。

---

## 6. 核心设计原则

### 6.1 状态显式化，不靠上下文记忆

模型不被要求"记住"第 12 章发生了什么。所有跨章事实都被抽成结构化 YAML，经 Pydantic 校验，每次生成前重新加载。上下文窗口只承载**当前这一章需要的那一部分**。

### 6.2 压缩是降级，不是截断

[`StoryBibleCompressor`](../../meta_writing/story_bible/compressor.py) 不做尾部截断，而是三级降级：

| 级别 | 触发条件 | 策略 |
|------|----------|------|
| `full` | ≤15K token | 活跃角色全档案 + 时间线 + 世界规则 + 伏笔 + 爽点排期 |
| `summarized` | 超预算 | 前 3 位主角保留全档案，其余压成 2-3 句；砍掉世界规则与爽点排期 |
| `minimal` | 仍超预算 | 只留 POV 角色 + 即将到期的伏笔 |

即使降到 `minimal`，**即将到期的伏笔仍然保留**——因为伏笔失效是不可逆的叙事损伤，而配角细节的丢失只是当章质感下降。

### 6.3 双层质量闸门：确定性在前，模型在后

- **第一层**：[`style_linter.py`](../../meta_writing/style_linter.py) —— 纯正则，零 API 成本，零延迟。抓的是可枚举的 AI 腔：`那……很……，但……` 脚手架、`不是……是……` 反向下定义、连续单字成段、物体"记得"的拟人化。命中 `ERROR` 直接阻塞。
- **第二层**：三位 LLM 审稿各自出一张五维评分卡，加权聚合后过硬门槛。

先跑确定性检查的理由很实际：它免费，而且能抓到的问题 LLM 审稿经常懒得提。

### 6.4 多审稿人，加权聚合，双重门槛

三位审稿人（连续性 / 文风 / 第三编辑）各自独立打五个维度：

| 维度 | 权重 |
|------|------|
| `plot_tension` 剧情张力与节奏 | 30% |
| `characters` 人物塑造与互动 | 25% |
| `info_design` 信息量与暗线设计 | 20% |
| `language` 语言与描写质感 | 15% |
| `instruction_fit` 指令满足与完成度 | 10% |

聚合方式是**先按维度跨审稿人取平均，再加权求和**——不是先算各人总分再平均。这让某位审稿人在自己不擅长的维度上的极端打分被稀释，而不是直接拉动总分。

门槛是双重的：综合分 ≥ **8.0**，且**没有任何单维 < 7.0**。只有综合分门槛的话，剧情 9.5 分可以把人物 5 分背过线——而"人物塌了但剧情爽"恰恰是长篇最致命的失败模式。

### 6.5 修订循环必须能停下来

三个退出条件，缺一不可：

- `passed` —— 全部闸门通过
- `stalled_below_threshold` —— 连续 2 轮提升都 < 0.2 分，判定修不动了
- `max_revisions_reached` —— 到第 5 轮强制退出

停滞判断（[`editorial_progress_stalled`](../../meta_writing/editorial_scorecard.py)）是关键：没有它，一章在 7.8 分附近能空转五轮，烧掉五倍 token 却毫无进展。**修不动就应该交回给人，而不是继续磨。**

### 6.6 风格档案：同一套引擎，不同的审美口径

[`prompt_profiles.py`](../../meta_writing/prompt_profiles.py) 按创作指导文本里的关键词自动识别项目风格：

| 档案 | 触发关键词 | 第三编辑模式 |
|------|-----------|-------------|
| `literary_microfeel` 克制微感文学 | 克制美学、微感、留白、纯感官、不解释 | `literary_theme` |
| `tomato_romance` 番茄快节奏女频 | 番茄、高梗密度、快节奏、爽点、拉扯、女频 | `story` |
| `generic` 通用 | （兜底） | `story` |

档案不改代码路径，只往 Planner / Writer / 扩写 / 修订 / 连续性五处 system prompt 追加约束段落，并决定第三编辑用哪套审稿口径。这样"番茄项目被文学化标准误伤"这类问题可以在档案层解决，不必动引擎。

### 6.7 反例注入：与其事后修，不如别写出来

[`negative_examples.py`](../../meta_writing/negative_examples.py) 收录从真实编辑中提取的 bad→good 配对，在写作与扩写的 prompt 里直接展示。目前仅 `literary_microfeel` 档案启用。

这与 style linter 是同一批规则的两个投放时机：linter 在事后抓，反例在事前防。

---

## 7. 稳健性设计

LLM 返回结构化 JSON 是不可靠的，系统在四处做了防御：

| 位置 | 策略 |
|------|------|
| `PlannerAgent` | 提取代码块 → 直接解析 → 正则修复（去尾逗号、转义换行）→ 全文重试 → **调 LLM 修 JSON**（一次）→ 兜底成单分支 |
| `ContinuityAgent` | 多策略提取 → 解析失败则返回 `passed=True` + 一条 INFO 提示人工检查（不阻塞流程） |
| `StyleAgent` / `ThemeAgent` | 多策略提取 → 解析失败则返回空 issues + `scorecard=None` |
| `aggregate_editorial_scorecards` | 忽略 `None` 评分卡；全部为 `None` 时返回 0 分（必然不过门槛） |

设计取向是明确的：**解析失败不应该炸掉整条流水线，但也不应该被静默当成通过**。连续性审查解析失败时放行并留痕，评分卡缺失时算 0 分——前者是"看不出问题"，后者是"没打分"，处理方式不同。

LLM 调用层（[`llm.py`](../../meta_writing/llm.py)）统一 3 次重试、指数退避（2/4/8 秒），只对限流、连接错误和 5xx 重试；4xx 直接抛出。长文生成走流式以保活连接，超时设到 600 秒。

---

## 8. 相关文档

| 主题 | 文档 |
|------|------|
| 状态层：Story Bible 的模型与压缩 | [`story-bible.md`](story-bible.md) |
| 智能体层：六个 agent 的职责与契约 | [`agents.md`](agents.md) |
| 编排层：两条链路的完整对比 | [`pipelines.md`](pipelines.md) |
| 模型路由与供应商回退 | [`model-routing.md`](model-routing.md) |
| 评分体系的维护与调参 | [`../operations/editorial-scorecard-maintenance.md`](../operations/editorial-scorecard-maintenance.md) |
