# 手动章节工作流

面向**质量敏感的长期项目**的推荐循环。每一章的状态更新都经过人确认，不会出现「写到第 30 章才发现第 12 章的状态就错了」。

---

## 1. 为什么保留人工闸门

系统有三处刻意交给人的决策点，而不是交给 LLM：

| 环节 | 交给 LLM 的失效模式 |
|------|-------------------|
| 选分支 | 倾向选「安全」分支，长期导致剧情平淡 |
| 章节验收 | `stalled` / `max_revisions` 的章节会直接落盘 |
| 状态更新 | 抽取错误会累积，且没有人看得见 |

第三条最危险。Story Bible 的错误不会立刻显形——它在十几章之后以「角色行为不一致」的形式爆发，那时已经很难回溯是哪一章写坏的。

代价是每章多花几分钟。

> 早期存在一条全自动链路 `auto_runner.py`（LLM 选枝、无人工闸门、LLM 直接写回 Story Bible），已于 2026-09-09 移除。

## 2. 单章循环

### 步骤 1：准备上下文

开写前先读四样东西，确认自己知道这一章要接什么：

- 上一章正文 `chapters/NNN.md`
- `creator_guidance.md`
- `learned_rules.md`
- 相关的 Story Bible 文件（当前活跃角色卡、`foreshadowing.yaml`）

用 `status` 快速看伏笔年龄：

```powershell
meta-writing --project <name> status
```

**重点看「活跃伏笔」表的年龄列。** 接近 `foreshadowing_max_age_chapters - 5` 的伏笔应当在本章或紧接的几章内回收。

### 步骤 2：生成

```powershell
meta-writing --project <name> generate --guidance "本章要求：……"
```

`--guidance` 会与 `creator_guidance.md` 合并。写具体的本章目标，不要重复已经在 `creator_guidance.md` 里的长期约束。

### 步骤 3：选分支

三个判断维度，按重要性排序：

1. **伏笔回收** — 有临期伏笔时，优先选包含回收机会的分支
2. **张力走向** — 连续几章 `tension_increase` 之后应该有一次回落，反之亦然
3. **风险等级** — `bold` 分支值得偶尔选，全程 `safe` 会导致剧情平淡

不要只看大纲写得好不好——大纲的文采与成稿质量相关性很低。

### 步骤 4：审章节

在你看到正文之前，系统已经自动跑完了审稿-修订循环。**先看它的结论，再读正文**。

CLI 会展示连续性问题。更完整的记录在 `editorial_reviews/NNN.md`（此时已写盘）：

```powershell
Get-Content novels/<name>/editorial_reviews/NNN.md
```

按 `final_decision` 决定怎么读：

| 取值 | 怎么处理 |
|------|---------|
| `passed` | 正常通读，重点看是否符合本章意图 |
| `stalled_below_threshold` | **重点读低分维度对应的部分**。系统已经判定修不动了 |
| `max_revisions_reached` | 同上，且说明问题较顽固，考虑改 guidance 重生成 |

然后选择：

- `approve` — 接受
- `edit` — 输入的文本**整体替换**正文（不是打补丁），适合你已在编辑器里改好、整段粘回来
- `reject` — 放弃本章，不落盘。适合分支选错了想重来

### 步骤 5：确认状态变更

`ContinuityAgent` 检出的角色状态变化会以表格呈现。**逐条核对**，不要习惯性按 `y`：

- 角色名拼错的变更会被静默丢弃（不会报错）
- schema 里不存在的字段名同样被静默丢弃
- 确认写入后只改内存对象，随后整本 Story Bible 写盘

---

## 3. 落盘后的人工补齐

自动流程做完之后，有三件事需要人补。**这是手动工作流不可省略的部分。**

### 3.1 修正章节摘要

系统自动写入的 `story_data/chapter_summaries/NNN.yaml` 中，`summary` 取自**规划时的大纲前 200 字**，不是成稿摘要。若章节在修订中偏离了原大纲，它就是错的。

至少修正这三个字段：

```yaml
summary: "2-3 句真实剧情摘要"
characters_present: ["实际出场的角色"]   # 影响下一章的上下文选角
events: ["按顺序的关键事件"]
```

`characters_present` 尤其重要——下一章生成时，压缩器会从最近 3 章的这个字段推断活跃角色。**写错会导致下一章的上下文里缺人。**

### 3.2 更新 Story Bible

`ContinuityAgent` 只检出**角色状态**变更，其余全靠人工：

| 文件 | 什么时候要改 |
|------|------------|
| `characters/*.yaml` | 关系变化、知识状态变化、目标变化、成长阶段推进 |
| `timeline.yaml` | 本章发生了对后续有影响的事件 |
| `foreshadowing.yaml` | 埋了新伏笔（新增条目）/ 回收了伏笔（改 `status` 与 `payoff_*`）/ 强化了伏笔（追加 `reinforcement_chapters`） |
| `pacing.yaml` | 交付了排期中的爽点（`delivered: true`） |
| `world_rules.yaml` | 引入了新的世界设定或约束 |

漏更新伏笔状态的后果最严重：已回收的伏笔会继续出现在上下文里并触发到期告警，而 Planner 会反复尝试回收一个已经收过的伏笔。

### 3.3 沉淀规则

如果这一章暴露了一个**会重复出现**的问题，把它写进：

- `learned_rules.md` — 具体的、可操作的规则（「不要用 X 句式开场」）
- `creator_guidance.md` — 长期的审美约束（「本作对话以生活化短句为主」）

如果这个问题是可正则化的 AI 腔，考虑加进 style linter，见 [`../reference/style-rules.md`](../reference/style-rules.md)。

---

## 4. 验证

写完一章后，确认 Story Bible 仍然合法：

```powershell
@'
from pathlib import Path
from meta_writing.story_bible.loader import StoryBibleLoader
bible = StoryBibleLoader(Path("novels/<name>/story_data")).load()
print("current_chapter  =", bible.core.current_chapter)
print("characters       =", len(bible.characters))
print("chapter_summaries=", len(bible.chapter_summaries))
print("active foreshadow=", len(bible.active_foreshadowing()))
for f in bible.aging_foreshadowing(bible.core.current_chapter):
    print("  临期伏笔:", f.id, f.setup_description[:30], f"(已过{f.age_at(bible.core.current_chapter)}章)")
'@ | python -X utf8 -
```

加载失败通常是 YAML 手改出错——最常见的是角色卡缺 `core_triangle` 或 `motivation_type`。

---

## 5. 提交

**章节与它的状态更新必须一起提交。** 只有正文没有状态更新的提交视为不完整。

```powershell
git status --short
git diff --check
git add novels/<name>/chapters/NNN.md novels/<name>/story_data novels/<name>/editorial_reviews
git commit -m "chapter NNN: <一句话内容>"
```

系统在 `_commit_chapter()` 里会尝试自动 commit，但**失败是静默的**（不在 git 仓库、未配 user.email、无变更都不会报错）。养成 `git log -1 --stat` 确认的习惯。

---

## 6. 周期性复盘

每 5–10 章做一次，成本很低但能提前发现结构性问题：

### 伏笔审计

```powershell
meta-writing --project <name> status
```

看「活跃伏笔」表：有没有年龄已经接近上限但一直没安排回收的？有的话在下一章的 `--guidance` 里点名。

### 审稿趋势

```powershell
Select-String -Path novels/<name>/editorial_reviews/*.json -Pattern '"final_decision"'
```

`stalled_below_threshold` 集中出现，说明质量标准与当前写法长期不匹配。两种应对：

- 改写法 → 更新 `creator_guidance.md` / `learned_rules.md`
- 改标准 → 见 [`../operations/editorial-scorecard-maintenance.md`](../operations/editorial-scorecard-maintenance.md)

**不要直接下调 `EDITORIAL_PASS_THRESHOLD` 了事**——先确认是不是审稿口径误伤（比如快节奏项目被文学化标准评判），那应该改风格档案而不是改门槛。

### 角色活跃度

检查 `last_active` 明显落后的角色：是有意的（该角色暂时退场）还是遗漏的（本该出场但被上下文压缩挤掉了）？后者可以通过在 `--guidance` 里点名角色来纠正。

---

## 7. 相关文档

- 流水线内部机制：[`../architecture/pipelines.md`](../architecture/pipelines.md)
- 为什么状态摘要会失真：[`../architecture/story-bible.md`](../architecture/story-bible.md)
- 评分门槛与调参：[`../operations/editorial-scorecard-maintenance.md`](../operations/editorial-scorecard-maintenance.md)
- 测试与发布卫生：[`../operations/testing-and-verification.md`](../operations/testing-and-verification.md)
