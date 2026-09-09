# Story Bible 字段参考

> 代码位置：[`meta_writing/story_bible/schema.py`](../../meta_writing/story_bible/schema.py)
> 设计说明：[`../architecture/story-bible.md`](../architecture/story-bible.md)

全部模型基于 Pydantic v2，加载时强校验。字段名即 YAML 键名。

---

## 文件对应关系

| YAML 路径 | 模型 | 必需 |
|-----------|------|------|
| `story_data/story_core.yaml` | `StoryCore` | **是** |
| `story_data/characters/*.yaml` | `Character`（每文件一个） | 否 |
| `story_data/timeline.yaml` | `list[TimelineEvent]` | 否 |
| `story_data/world_rules.yaml` | `list[WorldRule]` | 否 |
| `story_data/foreshadowing.yaml` | `list[ForeshadowingPair]` | 否 |
| `story_data/pacing.yaml` | `PacingState` | 否 |
| `story_data/chapter_summaries/NNN.yaml` | `ChapterSummary`（每文件一个） | 否 |

`story_core.yaml` 缺失时 `loader.load()` 抛 `ValidationError`；其余缺失均降级为空集合。

---

## StoryCore

```yaml
hook: "一句话核心"                    # 必填
genre: "现代言情"                     # 必填，见下方枚举
target_satisfaction_type: "核心爽点类型"
world_layers:
  - name: "表层世界 (日常)"
    description: "..."
    revealed_in_chapter: 3            # 可空
foreshadowing_max_age_chapters: 20
total_planned_chapters: 100           # 可空
current_chapter: 0                    # 最后完成的章号
chapter_target_chars: 2000            # 可空，≥800
chapter_min_chars: 1600               # 可空，≥500
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `hook` | str | — | 必填 |
| `genre` | `Genre` | — | 必填 |
| `target_satisfaction_type` | str | `""` | 同时参与[风格档案识别](../architecture/overview.md) |
| `world_layers` | list | `[]` | 五层世界架构 |
| `foreshadowing_max_age_chapters` | int | `20` | 伏笔告警阈值，到期前 5 章开始提示 |
| `total_planned_chapters` | int? | `None` | — |
| `current_chapter` | int | `0` | 由编排层在落盘时推进 |
| `chapter_target_chars` | int? | `None` | 约束 `ge=800`；为空则用 `TARGET_CHAPTER_CHARS=10000` |
| `chapter_min_chars` | int? | `None` | 约束 `ge=500`；为空则用 `MIN_CHAPTER_CHARS=7000` |

> 后两项为空时的兜底值（10000 / 7000）远高于 `meta-writing init` 的默认提示（2000）。长期项目建议显式写死这两个字段。

### Genre 枚举

`玄幻仙侠` `都市异能` `悬疑推理` `科幻未来` `惊悚悬疑` `无限流` `历史军事` `现代言情` `古代言情` `青春校园`

> `init` 命令按体裁给伏笔寿命默认值时，查表的键是 `玄幻仙侠` / `言情` / `悬疑推理`。其中 `言情` **不是** `Genre` 的合法值（实际值为 `现代言情` / `古代言情`），因此言情项目命中的是兜底值 20 而非预期的 15。需要 15 请手动填写。

---

## Character

一个角色一个 YAML 文件，文件名由 `name.replace(" ", "_").lower()` 生成。

```yaml
name: "林月"                          # 必填
aliases: ["月姐"]
physical_description: "..."
personality_traits: ["谨慎", "嘴硬"]
knowledge_state: "角色当前知道什么"
emotional_state: "当前情绪状态"
relationships:
  - target: "沈砚"
    type: "师徒"
    description: "..."
    knowledge: "她对沈砚了解到什么程度"
current_goals: ["..."]
location: "当前位置"

core_triangle:                        # 必填
  desire: "想要什么"
  ability: "能做什么"
  obstacle: "什么挡路"
motivation_type: "emotional"          # 必填
growth_stage: "initial"
backstory: "隐藏背景（作者知道，角色未必知道）"

first_appearance: 1
last_active: 1
is_pov: false
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `name` | str | — | 必填，同时是 `StoryBible.characters` 的键 |
| `core_triangle` | `CoreTriangle` | — | **必填**，三个子字段都必填 |
| `motivation_type` | `MotivationType` | — | **必填** |
| `growth_stage` | `GrowthStage` | `initial` | — |
| `knowledge_state` | str | `""` | 角色**知道**什么，与 `backstory` 严格区分 |
| `backstory` | str | `""` | 作者知道的隐藏背景 |
| `is_pov` | bool | `false` | 影响压缩时的保留优先级 |
| `first_appearance` / `last_active` | int | `1` | 用于识别长期消失的角色 |

枚举取值：

- `MotivationType`：`survival` `emotional` `interest` `mission` `curiosity`
- `GrowthStage`：`initial` `triggered` `adapting` `crisis` `transformed`

> `core_triangle` 与 `motivation_type` 是仅有的两个无默认值的字段。老角色卡缺这两项会导致整本 Story Bible 加载失败。

---

## TimelineEvent

```yaml
- chapter: 12
  description: "..."
  characters_involved: ["林月"]
  location: "..."
  significance: "为什么这件事对剧情重要"
```

压缩器按 `chapter >= current_chapter - lookback` 过滤（`full` 级回看 10 章，`summarized` 级 5 章）。

---

## WorldRule

```yaml
- name: "淬体境界"
  category: "magic_system"            # magic_system | geography | social | technology
  description: "..."
  constraints:                        # 不可违反的硬约束
    - "境界不可跨级越阶"
  introduced_chapter: 5               # 可空
```

`constraints` 会以「硬性约束」标题写进上下文，是 `ContinuityAgent` 判断「世界规则违反」的依据。

> 世界规则**只在 `full` 压缩级别进入上下文**。故事状态膨胀后会最先被丢弃。关键约束建议同时写进 `creator_guidance.md`。

---

## ForeshadowingPair

```yaml
- id: "fs_001"                        # 必填，唯一
  setup_description: "埋了什么"       # 必填
  setup_chapter: 3                    # 必填
  payoff_description: "怎么收的"
  payoff_chapter: 27                  # 可空
  status: "planted"
  reinforcement_chapters: [9, 15]
  priority: "normal"                  # high | normal | low
```

`status` 取值：`planted` `reinforced` `paid_off` `abandoned`。前两者算「活跃」，进上下文。

年龄 = `current_chapter - setup_chapter`。达到 `foreshadowing_max_age_chapters - 5` 即触发 `⚠️ 即将到期!` 告警。

> `priority` 字段在全仓库范围内**只被 schema 定义，无任何读写方**——压缩器、审稿提示词、编排层都不引用它。它是预留字段。

---

## PacingState

```yaml
beats:
  - chapter: 12
    beat_type: "medium"               # minor | medium | major
    description: "..."
    delivered: false
hooks:
  - chapter: 12
    hook_type: "reversal"             # suspense | conflict | emotional | reversal
    description: "..."
    position: "end"                   # end | mid | start
tension_curve: [3.0, 4.5, 6.0]        # 逐章张力 0-10
```

压缩器只取**未交付且章号 ≥ 当前章**的前 5 个 `beats`。

> `hooks` 与 `tension_curve` **当前无任何读写方**——压缩器不读取它们，因此不会进入任何 agent 的上下文。（此前由已移除的自动链路写入。）目前仅作为人工规划的记录字段。

---

## ChapterSummary

一章一个 YAML 文件，文件名为三位零填充章号（`001.yaml`）。

```yaml
chapter_number: 12                    # 必填
title: "..."
summary: "2-3 句剧情摘要"             # 必填
events: ["按顺序的关键事件"]
characters_present: ["林月", "沈砚"]
state_changes:
  - character: "林月"
    field: "emotional_state"
    old_value: "戒备"
    new_value: "松动"
new_information_revealed: ["..."]
foreshadowing_planted: ["fs_007"]
foreshadowing_paid_off: ["fs_001"]
pov_character: "林月"
word_count: 2143
```

`characters_present` 有实际作用：压缩器在调用方未指定活跃角色时，从最近 3 章的这个字段取并集。**摘要缺失或角色名写错，会直接导致下一章的上下文选错角色。**

> 编排层自动写入的 `summary` 取自规划大纲前 200 字，非成稿摘要。修订幅度大时需人工修正，详见 [`../architecture/story-bible.md`](../architecture/story-bible.md)。

---

## 项目元数据

`.meta-writing-project.json`（不属于 Story Bible，但与其同级）：

```json
{ "name": "rescue-male-lead" }
```

只记录项目名。文件缺失时 `read_project_metadata()` 返回 `None`，项目名回落为目录名。
