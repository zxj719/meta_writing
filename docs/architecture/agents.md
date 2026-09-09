# 智能体层

> 代码位置：[`meta_writing/agents/`](../../meta_writing/agents/)

系统有五个常驻 agent，分成生成侧与审稿侧。自动链路另有三个辅助 agent，定义在 [`auto_runner.py`](../../auto_runner.py) 内部。

| Agent | 侧 | 职责 | 输出 | 温度 |
|-------|-----|------|------|------|
| `PlannerAgent` | 生成 | 产出 2-3 条剧情分支 | JSON | 0.8 |
| `WriterAgent` | 生成 | 写正文 / 扩写 / 修订 | 纯文本 | 0.7（修订 0.5） |
| `ContinuityAgent` | 审稿 | 连续性与信息流 | JSON + 评分卡 | 0.3 |
| `StyleAgent` | 审稿 | 文风与描写质感 | JSON + 评分卡 | 0.3 |
| `ThemeAgent` | 审稿 | 剧情/人物/暗线/完成度 | JSON + 评分卡 | 0.3 |

温度分层是明确的：生成侧要多样性（0.7–0.8），审稿侧要稳定可复现（0.3），修订要忠实于原文（0.5）。

---

## 1. 通用契约

所有 agent 遵循同一组约定：

**构造**：`Agent(llm_client, model=...)`。agent 不自己创建 client——由编排层注入，这正是同一批 agent 能在两条链路上跑不同模型路由的原因。

**system prompt 组装**：每个 agent 暴露一个 `build_*_system_prompt(prompt_profile)` 函数，把基础提示词与风格档案的追加段落拼接：

```python
def build_writer_system_prompt(prompt_profile=None):
    profile = prompt_profile or GENERIC_PROFILE
    sections = [WRITER_BASE_SYSTEM_PROMPT.strip()]
    if profile.writer_notes.strip():
        sections.append(profile.writer_notes.strip())
    return "\n\n".join(sections)
```

这些函数是模块级的、无副作用的，可以在测试里直接断言提示词内容。

**结果对象**：每个 agent 返回一个 dataclass，其中保留 `raw_response: LLMResponse`——原始响应始终可追溯，token 用量可统计。

**降级**：JSON 解析失败不抛异常，返回一个语义安全的降级结果。详见各节。

---

## 2. 生成侧

### 2.1 PlannerAgent

产出 2-3 条**走向明显不同**的剧情分支，每条包含大纲（500-800 字）、涉及角色、后果、伏笔机会、爽点级别、钩子类型、张力影响、风险等级。

系统提示词里的五条核心原则：三幕式结构、爽点分布、钩子技术、角色驱动、**伏笔管理**（有即将到期的伏笔时，至少一个分支必须含回收机会）。

**JSON 稳健性是这个 agent 最重的部分**，共五层防御：

```
1. _extract_json_block()   ```json 块 → ``` 块 → 最外层配对花括号
2. json.loads()            直接解析
3. _repair_json_string()   去尾逗号、转义字符串内换行，再解析
4. 对全文重跑步骤 3        （防止步骤 1 提取错位置）
5. _retry_json_repair()    把坏 JSON 发回 LLM，temperature=0.1，要求只输出合法 JSON
   └─ 仍失败 → _fallback_branch()：把原始文本整个塞进单个分支的 outline
```

第 5 层只在前四层全败时触发，且只重试一次。兜底分支的 `title` 固定为 `"未能解析的分支"`——这个字符串同时是触发第 5 层的**哨兵值**，编排层据此判断是否需要修复。

### 2.2 WriterAgent

三个方法，共用同一个 client，但各有独立的 system prompt：

| 方法 | 用途 | max_tokens | 温度 |
|------|------|-----------|------|
| `write()` | 从大纲写初稿 | 16384 | 0.7 |
| `expand()` | 字数不足时扩写 | 16384 | 0.7 |
| `revise()` | 按审稿反馈修订 | 16384 | 0.5 |

`write_with_expansion()` 把前两个串成两阶段：

```python
result = await self.write(...)
if _count_chinese_chars(result.chapter_text) >= min_chars:
    return result
return await self.expand(..., target_chars=target_chars)
```

只扩写一次，不循环——扩写的边际收益递减很快，第二次扩写通常只是灌水。

字数阈值：模块默认 `MIN_CHAPTER_CHARS = 7000` / `TARGET_CHAPTER_CHARS = 10000`，但编排层会用 `StoryCore.chapter_min_chars` / `chapter_target_chars` 覆盖（若项目设了的话）。**这两组默认值与 `meta-writing init` 交互式提示的默认值（2000 字目标）差距很大**——init 的默认更贴近实际使用，模块常量只是没被项目配置覆盖时的兜底。

三个 system prompt 里的禁止清单是系统最厚的一层质量约束，与 [`style_linter.py`](../../meta_writing/style_linter.py) 的规则一一对应。写作提示词额外注入 [`negative_examples`](../../meta_writing/negative_examples.py) 的 bad→good 配对（最多 8 条，仅对配置了 `negative_examples_profile` 的档案生效）。

**注意**：`write()` 里创作指导被拼接了两次——`_build_write_prompt()` 内部不含 guidance，但方法体又追加了一段 `## 创作指导`。实际行为是 guidance 在用户消息末尾出现一次，符合预期。

---

## 3. 审稿侧

三位审稿人**各自独立**评审同一份正文，各返回一张五维评分卡。它们不互相看对方的意见——这是刻意的，避免锚定效应。

### 3.1 ContinuityAgent

七个检查项：角色状态矛盾、关系状态矛盾、时间线矛盾、世界规则违反、伏笔审计、角色动机、**信息流向**。

最后一项是最容易被忽视也最致命的：*"角色说出口或做出来的判断，是否真有合理的信息来源"*。提示词里写死了对应的判断标准：**"作者知道"不等于"角色知道"，严格区分**。

除 issues 外，它还负责检出 `state_changes_detected`——这是手动链路更新角色状态的**唯一自动来源**。

解析失败时的降级值得注意：

```python
return ContinuityResult(
    passed=True,                    # 不阻塞
    issues=[... severity=INFO, "连续性审查输出解析失败，请人工检查。"],
    scorecard=None,                 # 但不贡献分数
)
```

`passed=True` 是"看不出问题"，不是"确认没问题"，因此配一条 INFO 留痕。而 `scorecard=None` 会让这位审稿人被排除在聚合之外。

### 3.2 StyleAgent

六个审查重点：机械语言模式、说话方式元注释、描写缺口、结构回声、节奏单一、比喻老套或堆叠。

两条量化判据写进了提示词：

- *"偶发一次不算问题，频率过高才算"*
- *"如果外貌、神态、环境三项里至少两项明显缺失，应至少提出 warning"*

**结构回声检测**需要额外输入——编排层会把上一章结尾的最后 400 字传进来：

```python
prev_text = prev_path.read_text(encoding="utf-8")
prev_ending = prev_text[-400:] if len(prev_text) > 400 else prev_text
```

这是为了抓"连续两章用相同结尾句式"——一个 linter 抓不到、但读者一眼能感觉到的问题。

`build_style_system_prompt()` 复用风格档案的 `revision_notes`（而非独立的 style 字段），把它作为"当前项目修订约束"追加。

### 3.3 ThemeAgent（第三编辑）

**唯一一个有两套人格的 agent**，由风格档案的 `third_editor_mode` 决定：

| 模式 | 提示词 | 关注 |
|------|--------|------|
| `story`（默认） | `STORY_EDITOR_PROMPT` | 是否在推进故事、人物是否像活人、信息是否藏在动作里、是否回应了创作指令、过渡章是否仍有可读性 |
| `literary_theme` | `LITERARY_THEME_PROMPT` | 主题推进、克制性、人物弧线位置、意象层次、跨章模式重复 |

`story` 模式的判断标准里有一条很实用的平衡表述：*"普通生活章可以松，但松弛不等于无事发生"*，以及 *"要特别警惕'为了满足要求，硬插一段'的痕迹"*——后者专门针对修订循环自身可能引入的伤害。

它还有一个未被编排层调用的方法 `review_arc()`，对一段章节区间做跨章审查（每章取前 500 字）。目前只能手动调用。

> **命名说明**：这个 agent 在代码里叫 `ThemeAgent`，在提示词和审稿输出里叫"第三编辑"。默认的 `story` 模式其实做的是剧情/人物/完成度审查，与"主题"关系不大——只有 `literary_theme` 模式名副其实。[`../operations/editorial-scorecard-maintenance.md`](../operations/editorial-scorecard-maintenance.md) 中已记录改名建议。

---

## 4. 自动链路专属 agent

以下三个定义在 [`auto_runner.py`](../../auto_runner.py) 内，替代手动链路中的人工环节：

| Agent | 替代的人工环节 | 输出 |
|-------|---------------|------|
| `BranchSelector` | 终端里选分支 | 分支序号 + 选择理由 |
| `BibleUpdater` | 确认并写回状态变更 | 直接写 Story Bible YAML |
| `LessonAccumulator` | 人手写 `learned_rules.md` | 追加新规则 |

另有一个非 agent 的机制 `CarryoverCorrection`：把上一章审稿中未解决的问题序列化到 `.auto_runner_correction.json`，在下一章生成时**置于创作指导最前**。这让自动循环具备跨章自我纠偏能力——手动链路没有对应物，因为人会自己记得上一章的问题。

---

## 5. 扩展一个新 agent

如果要加第四位审稿人，需要动四个地方：

1. **新建** `meta_writing/agents/<name>.py`，遵循 §1 的通用契约，system prompt 拼接 `EDITORIAL_SCORECARD_PROMPT` 以产出评分卡
2. **注册进编排层**：`Orchestrator.__init__` 构造实例，审稿循环里调用，把 `result.scorecard` 加进 `aggregate_editorial_scorecards([...])`
3. **接进阻塞判定**：在 `blockers` 与 `review_passed` 的布尔表达式里加入新条件
4. **反馈拼接**：在 `feedback_parts` 里追加 `result.format_feedback()`

自动链路需要同样的四步。**两条链路的审稿逻辑目前是各自实现的，没有共享抽象**——这是当前架构最主要的重复点，加审稿人时必须两边都改。
