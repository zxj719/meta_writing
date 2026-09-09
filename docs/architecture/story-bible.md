# 状态层：Story Bible

> 代码位置：[`meta_writing/story_bible/`](../../meta_writing/story_bible/)
> 字段级参考：[`../reference/story-bible-schema.md`](../reference/story-bible-schema.md)

Story Bible 是整个系统的真相来源（single source of truth）。所有跨章一致性——角色状态、时间线、世界规则、伏笔、节奏——都不依赖模型记忆，而是显式落在磁盘上的结构化 YAML。

模块分三层职责：

| 文件 | 职责 |
|------|------|
| [`schema.py`](../../meta_writing/story_bible/schema.py) | Pydantic 模型定义与校验 |
| [`loader.py`](../../meta_writing/story_bible/loader.py) | YAML 读写、路径约定、聚合装载 |
| [`compressor.py`](../../meta_writing/story_bible/compressor.py) | 按 token 预算三级降级压缩 |

---

## 1. 数据模型

`StoryBible` 是内存中的聚合根，磁盘上则拆成多个 YAML 文件：

```
StoryBible
├── core: StoryCore                          → story_core.yaml
├── characters: dict[str, Character]         → characters/*.yaml（每角色一文件）
├── timeline: list[TimelineEvent]            → timeline.yaml
├── world_rules: list[WorldRule]             → world_rules.yaml
├── foreshadowing: list[ForeshadowingPair]   → foreshadowing.yaml
├── pacing: PacingState                      → pacing.yaml
└── chapter_summaries: dict[int, ...]        → chapter_summaries/NNN.yaml（每章一文件）
```

**拆分粒度是刻意的**：角色卡和章节摘要一文件一实体，因为它们是高频、独立更新的；时间线、世界规则、伏笔是整体读写的列表，合成单文件。这个粒度直接决定了 git diff 的可读性——改一个角色的情绪状态，diff 里只出现那一个文件。

### 1.1 角色：核心三角 + 成长阶段

`Character` 的设计不是普通的属性袋，它内嵌了一套创作方法论：

```yaml
core_triangle:          # 角色核心三角
  desire:   想要什么
  ability:  能做什么
  obstacle: 什么挡路
motivation_type: survival | emotional | interest | mission | curiosity
growth_stage:    initial | triggered | adapting | crisis | transformed
```

三角形被压缩器**无条件写进上下文**（连 `minimal` 级别也保留），因为它是审稿时判断"这个行为符不符合角色"的唯一依据——`ContinuityAgent` 的检查项之一就是"行为是否尊重角色的欲望/能力/阻碍三角"。

另外区分了两组易混字段：

- `knowledge_state`（角色**知道**什么）vs `backstory`（作者知道、角色未必知道的隐藏背景）。连续性审查里有一条硬规则：**"作者知道"不等于"角色知道"**。
- `first_appearance` / `last_active`：用于识别长期消失的角色。

### 1.2 伏笔：带寿命的契诃夫之枪

`ForeshadowingPair` 把"埋"和"收"绑成一对，并引入**寿命**概念：

```python
status: planted | reinforced | paid_off | abandoned
age_at(current_chapter) = current_chapter - setup_chapter
```

`StoryCore.foreshadowing_max_age_chapters` 定义该体裁的伏笔最大寿命（玄幻 30 / 言情 15 / 悬疑 20，默认 20）。`aging_foreshadowing()` 在**到期前 5 章**就开始告警：

```python
f.age_at(current_chapter) >= threshold - 5
```

提前 5 章而不是到期才报，是因为伏笔回收需要提前铺垫，到期当章才发现已经来不及自然收束。

告警会以 `⚠️ 即将到期!` 的形式直接出现在压缩后的上下文里，Planner 的系统提示词里也有对应约束："如果有即将到期的伏笔，至少一个分支必须包含回收机会"。

### 1.3 节奏：爽点排期与张力曲线

`PacingState` 记录三样东西：

- `beats`：爽点排期（`minor` 每章 / `medium` 弧线中点 / `major` 弧线高潮），带 `delivered` 标记
- `hooks`：章节边界的钩子（悬念 / 冲突 / 情感 / 反转）
- `tension_curve`：逐章张力值 0-10

压缩器只把**未交付且在当前章之后**的前 5 个爽点写进上下文——已交付的和过期的对写下一章没有价值。

---

## 2. 装载与持久化

[`StoryBibleLoader`](../../meta_writing/story_bible/loader.py) 是唯一的磁盘出入口。

- 构造时即 `mkdir` 出 `characters/` 与 `chapter_summaries/`，后续读写不必再判断目录存在。
- 单组件读写（`load_core` / `save_character` / …）与整体读写（`load` / `save`）并存。`load()` 在 `story_core.yaml` 缺失时抛 `ValidationError`——**故事核心是唯一的必需文件**，其余缺失都降级为空集合。
- YAML 统一 `allow_unicode=True, sort_keys=False, width=120` 写出：中文不转义、字段顺序按 schema 声明而非字母序、行宽 120。这三个设置全部是为了让 diff 可读。
- 角色文件名由 `name.replace(" ", "_").lower()` 生成。**注意**：中文角色名不会被转写，文件名即中文。

---

## 3. 上下文压缩

这是整个状态层最核心的机制。默认预算 **15000 token**。

### 3.1 token 估算

```python
chinese_chars / 1.5 + other_chars / 4
```

一个粗略但足够用的启发式：中文约 1.5 字/token，其他字符约 4 字/token。系统不调用真实 tokenizer——估算偏差被 15K 预算本身的余量吸收了。

### 3.2 三级降级

压缩器**依次尝试**三个级别，取第一个进预算的：

| | `full` | `summarized` | `minimal` |
|---|---|---|---|
| 故事核心 | 完整（含五层世界架构） | 完整 | 精简（hook + 体裁 + 当前章） |
| 角色 | 全部活跃角色，全档案 | 前 3 位全档案，其余 2-3 句 | 仅 POV 角色 |
| 时间线 | 回看 10 章 | 回看 5 章 | — |
| 世界规则 | 全部（含硬性约束） | — | — |
| 伏笔 | 全部活跃 + 到期告警 | 全部活跃 + 到期告警 | **仅即将到期的** |
| 爽点排期 | 未来 5 个 | — | — |

丢弃顺序体现了优先级判断：**世界规则和爽点排期最先被砍，伏笔最后被砍**。理由在 [`overview.md §6.2`](overview.md) 说过——伏笔失效是不可逆的叙事损伤。

### 3.3 活跃角色的推断

调用方可以显式传 `active_character_names`。不传时，压缩器从**最近 3 章的章节摘要**里取并集；若摘要也为空（比如第 1 章），退化为取前 5 个角色。

手动链路对此做了两阶段利用：

```python
# 规划前：不知道谁会出场，让压缩器自己推断
bible_context = self.compressor.compress(bible, chapter_number, pov_character=None)

# 分支选定后：角色名已知，重新压缩得到更聚焦的上下文
bible_context = self.compressor.compress(
    bible, chapter_number,
    active_character_names=selected_branch.characters_involved,
)
```

---

## 4. 状态更新路径

Story Bible 的写回有三条路径，可靠性依次递减：

| 路径 | 触发者 | 人工确认 |
|------|--------|----------|
| 人工编辑 YAML | 人 | — |
| `ContinuityAgent` 检出 `state_changes_detected` | 手动链路 | **需要**（`state_confirmer` 回调） |
| `BibleUpdater` LLM 直接写回 | 自动链路 | 无 |

手动链路里，即使确认了状态变更，`_apply_state_changes` 也只对**已存在的角色**和**schema 里真实存在的字段**生效：

```python
character = bible.characters.get(change["character"])
if character is None:
    continue
if hasattr(character, field_name):
    setattr(character, field_name, change["new_value"])
```

不存在的角色名和拼错的字段名被静默丢弃，不会污染状态。

此外 `_commit_chapter` 无条件推进两个字段：`core.current_chapter` 与该章的 `ChapterSummary`。**注意当前实现的一个局限**：这里写入的摘要是 `selected_branch.outline[:200]`，即规划时的大纲前 200 字，而不是成稿后的真实内容摘要。若章节在修订中偏离了原大纲，摘要会失真。手动工作流因此要求人工补写 `story_data/chapter_summaries/NNN.yaml`。

---

## 5. 可选：向量检索

[`vector_store/store.py`](../../meta_writing/vector_store/store.py) 提供 ChromaDB + BGE-M3 的章节语义检索（"找出 X 发生的那一章"）。

- 按场景分块：先按场景分隔符（`***` / `---` / 空行三连）切，超长场景再按段落切，过短块合并。目标 700 字/块，上下限 300–1200。
- 嵌入模型**惰性加载**（BGE-M3 需 ~2.2GB 显存），不查询就不加载。
- `update_chapter()` 先删旧块再写新块，避免章节修订后新旧内容同时命中。

**当前它没有被任何链路调用**——`orchestrator.py` 和 `auto_runner.py` 都不引用它。近期章节是直接读文件全文喂进上下文的（回看 3 章）。向量检索是为超长篇（章节数远超上下文容量）预留的能力，目前处于"已实现、未接线"状态。
