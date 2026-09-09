# 文风规则参考

> 代码位置：[`meta_writing/style_linter.py`](../../meta_writing/style_linter.py)、[`meta_writing/negative_examples.py`](../../meta_writing/negative_examples.py)

文风约束在三个时机投放：

| 时机 | 机制 | 成本 |
|------|------|------|
| **事前** | 反例库注入写作/扩写 prompt | 提示词 token |
| **事前** | Writer/扩写/修订 system prompt 的禁止清单 | 提示词 token |
| **事后** | Style Linter 正则扫描 | 零 |
| **事后** | StyleAgent LLM 审稿 | 一次 API 调用 |

Linter 与反例库是同一批规则的两个投放时机——linter 抓漏网的，反例防写出来。

---

## 1. Style Linter

三类规则，输出 `StyleIssue(line, text, pattern_name, message, suggestion, severity)`。

严重度语义：

| 级别 | 含义 | 是否阻塞修订循环 |
|------|------|-----------------|
| `ERROR` | 必须修，违反既定风格规则 | **是** |
| `WARNING` | 应该修，很可能是问题 | 否 |
| `INFO` | 值得复核，可能是有意为之 | 否 |

`format_feedback_for_writer()` **只输出 ERROR 级**——WARNING 和 INFO 不进修订反馈，避免反馈过长诱发整体重写。

### 1.1 行级规则

逐行匹配，命中即报。

| 规则名 | 级别 | 抓什么 |
|--------|------|--------|
| `object_remembers` | ERROR | 物体「记得」（沙发/门框/砚台等 24 个词 + `记得`）——拟人化解读 |
| `generic_remembers` | ERROR | `它记得` / `它们记得` |
| `object_speaking` | ERROR | 物体「在说话/在叫/在等」 |
| `mind_reading` | ERROR | `他/她……在想：` ——读心术 |
| `structural_header_residue` | ERROR | `**节点一**` 等规划标记残留进正文 |
| `this_too_template` | ERROR | `这……太……` 夸张模板 |
| `negation_definition_template` | ERROR | `不是……而是/是……` 反向下定义 |
| `flat_expression_template` | ERROR | `脸色沉下去` / `眼神冷下去` 扁平神态 |
| `na_intensifier_but_scaffold` | ERROR | `那……很……，但……` 机械转折 |
| `na_negation_but_scaffold` | ERROR | `那……不……，但……` 机械转折 |
| `emotional_statement` | WARNING | `她懂了那种孤独` 等直白情感陈述 |
| `she_doesnt_know` | INFO | `她不知道`（全文上限 3 次，见全局规则） |
| `speaking_style_meta` | INFO | `他说话的方式是……` 元注释 |

### 1.2 全局计数规则

对全文计数，超过上限才报，`line=0`。

| 规则名 | 上限 | 级别 | 抓什么 |
|--------|------|------|--------|
| `contrast_scaffold_overuse` | 6 | ERROR | `X，但/却/可 Y` 对照句 |
| `na_zhong_na_zhong_heavy` | 8 | ERROR | `是那种……的那种……` 嵌套 |
| `na_zhong_na_zhong` | 5 | WARNING | 同上，较轻档 |
| `short_sentence_tic_overuse` | 3 | WARNING | 独立成段的 `很X。` |
| `negation_parallelism_overuse` | 3 | WARNING | `不是……是……` 排比 |
| `she_doesnt_know_overuse` | 3 | WARNING | `她不知道` |
| `enn_overuse` | 3 | WARNING | `"嗯。"` 作为对话回应 |
| `scale_reporting_overuse` | 3 | WARNING | 刻度汇报，会让叙事退化成感知日志 |
| `confirmation_tic` | 2 | INFO | `可以。` / `稳的。` 独立确认句 |

> `na_zhong_na_zhong` 与 `na_zhong_na_zhong_heavy` 用**同一条正则**、不同阈值。出现 9 次以上会同时命中两条，报两个 issue。这是有意的分档设计。

### 1.3 结构规则

两条不走正则表的特殊检查：

| 函数 | 级别 | 抓什么 |
|------|------|--------|
| `_find_tiny_paragraph_triplets` | ERROR | 连续三次单字/双字成段（`停。` `别动。` `听。`）——空洞的「有力感」 |
| `_find_opening_yi_jiu_scaffold` | ERROR | **章节首个非标题行**用 `一……就……` 起手式 |

后者只检查第一个有效行就返回，不扫全文——它针对的是「每章都用同一种开场节拍」这个跨章问题。

---

## 2. 反例库

[`negative_examples.py`](../../meta_writing/negative_examples.py) 收录 17 组从真实编辑中提取的 bad→good 配对：

| 类别 | 条数 |
|------|------|
| 物体记得 | 3 |
| 拟人化 | 2 |
| 过度解释 | 2 |
| 科技术语 | 2 |
| 直白情感 | 2 |
| 她不知道 / 规划标记残留 / 刻度过度汇报 / 确认短句口头禅 / 说话方式元注释 / 结尾结构复制 | 各 1 |

每条含 `bad` / `good` / `why`，格式化后作为「已知反模式及修正」注入 Writer 与扩写的用户消息，**最多 8 条**。

启用条件：风格档案的 `negative_examples_profile` 非空。目前只有 `literary_microfeel` 档案配置了它（指向全量 `NEGATIVE_EXAMPLES`）。

> 番茄档案与通用档案**不注入反例**。它们的文风约束只靠 system prompt 的禁止清单与 linter。若要为番茄项目建反例库，在 `NEGATIVE_EXAMPLE_PROFILES` 里新增键，并在对应 `PromptProfile` 上设置 `negative_examples_profile`。

---

## 3. 提示词层的禁止清单

三段 system prompt 各有一份禁止清单，是系统最厚的一层文风约束：

| 提示词 | 位置 |
|--------|------|
| `WRITER_BASE_SYSTEM_PROMPT` | 21 条禁止项 |
| `EXPANSION_BASE_SYSTEM_PROMPT` | 13 条禁止项 |
| `REVISION_BASE_SYSTEM_PROMPT` | 8 条修改原则 |

覆盖的问题类型与 linter 高度重合，另加了 linter 抓不到的：

- 角色用相同情感反应面对不同情境
- 配角对主角的谄媚式崇拜
- 复制上一章的结尾句式或意象
- 排比式内心独白（三连问）
- 主要角色长期没有外貌记忆点或神态层次
- 只写情节逻辑，不写环境画面、微表情和身体反应

风格档案的 `writer_notes` / `expansion_notes` / `revision_notes` 会追加在这些清单之后。

---

## 4. 新增一条规则

### 加正则规则

1. 在 [`style_linter.py`](../../meta_writing/style_linter.py) 的 `_LINE_RULES` 或 `_GLOBAL_RULES` 追加元组
2. 在 `tests/test_style_linter.py` 加正例与**反例**（确保不误伤正常文本）
3. 若定为 ERROR，同步在 `WRITER_BASE_SYSTEM_PROMPT` 加对应禁止项——**否则模型会持续写出它，每章都触发一轮无谓修订**

第 3 步是最容易漏的：linter 只负责抓，不负责教。只加 linter 规则而不改提示词，等于把成本转嫁到修订循环上。

### 加反例

1. 在 `NEGATIVE_EXAMPLES` 追加 `StyleExample(category, bad, good, why)`
2. 确认目标档案的 `negative_examples_profile` 已指向该组
3. 注意 8 条上限——超出部分不会进提示词，新增时应替换掉已经不再出现的旧反例

### 调整某档案的口径

改 [`prompt_profiles.py`](../../meta_writing/prompt_profiles.py) 对应 `PromptProfile` 的 `*_notes` 字段即可，不需要动 agent 代码。

---

## 5. 相关文档

- 评分体系的调参：[`../operations/editorial-scorecard-maintenance.md`](../operations/editorial-scorecard-maintenance.md)
- StyleAgent 的审查口径：[`../architecture/agents.md`](../architecture/agents.md)
- 档案识别关键词：[`configuration.md`](configuration.md)
