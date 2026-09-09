# meta_writing

**本地优先的中文长篇小说生成引擎。**

一个 Python 包、一个 CLI、一棵磁盘上的文件树——没有服务端、没有数据库、没有部署环节。全部状态都是 git 可追踪的纯文本（YAML + Markdown）。

它要解决的不是「写出一章能读的文字」，而是长篇写作真正的三个难点：

| 难点 | 应对 |
|------|------|
| **状态漂移** —— 第 30 章与第 12 章矛盾 | Story Bible：结构化、可校验、每章更新的显式状态层 |
| **上下文溢出** —— 故事状态迟早超出窗口 | 三级降级压缩，把状态压进固定 token 预算 |
| **质量塌陷** —— 越写越像模型 | 确定性 linter + 三位 LLM 审稿 + 五维评分卡双重硬门槛 |

---

## 快速开始

需要 Python 3.12+ 与至少一个 MiniMax API key。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

$env:MINIMAX_API_KEY = "..."
python -m pytest -q                    # 全部 LLM 调用已 mock，不消耗额度
```

开一本新书并写出第一章：

```powershell
meta-writing --workspace-dir . project create my-novel --mode manual --activate
meta-writing --workspace-dir . --project my-novel init
# 填写 novels/my-novel/creator_guidance.md
meta-writing --workspace-dir . --project my-novel add-character
meta-writing --workspace-dir . --project my-novel generate --guidance "第一章：建立主角处境与核心矛盾。"
```

完整步骤与常见坑：[`docs/guides/getting-started.md`](docs/guides/getting-started.md)

---

## 系统构成

```
编排层    orchestrator.py（手动）  /  auto_runner.py（自动）
智能体层  Planner Writer ┃ Continuity Style Theme
质量层    style_linter · editorial_scorecard · negative_examples · prompt_profiles
状态层    story_bible/（schema · loader · compressor） · workspace · vector_store
```

一章的完整生命周期：

```
读 Story Bible → 压缩上下文 → 规划 2-3 条分支 → 选枝 → 写作（不足则扩写）
  → [ linter + 三位审稿 → 五维评分 → 未过则修订 ] × ≤5 轮
  → 审稿留痕 → 人工验收 → 落盘 + 状态回写 + git commit
```

设计原理与取舍：[`docs/architecture/overview.md`](docs/architecture/overview.md)

---

## 仓库结构

| 路径 | 内容 |
|------|------|
| `meta_writing/` | Python 包：CLI、编排、agent、Story Bible、文风检查、工作区管理 |
| `auto_runner.py` | 自动生成循环（仅限 `automatic` 模式项目） |
| `scripts/editorial_pass.py` | 对已有章节单独跑审稿 |
| `novels/<project>/` | 隔离的小说项目：章节、Story Bible、创作指导、审稿记录 |
| `docs/` | 项目文档，见下 |
| `tests/` | pytest 套件，LLM 调用全部 mock |

每个项目自持全部状态：

```
novels/<project>/
├── .meta-writing-project.json    项目名 + workflow_mode
├── creator_guidance.md           长期创作指导（人写，影响全部 agent）
├── learned_rules.md              累积的风格与连续性规则
├── chapters/NNN.md               正文
├── story_data/                   Story Bible（YAML）
└── editorial_reviews/NNN.{md,json}   逐章审稿留痕
```

---

## 两种工作流

每个项目在 `.meta-writing-project.json` 里声明 `workflow_mode`，两条链路**互斥**——防止自动循环覆写人工精修过的章节。

| | `manual` | `automatic` |
|---|---|---|
| 入口 | `meta-writing generate` | `python auto_runner.py --from N --to M` |
| 分支选择 / 验收 / 状态回写 | 人 | LLM |
| 适用 | 质量敏感项目（推荐） | 批量产出、工具实验 |

对比详情：[`docs/architecture/pipelines.md`](docs/architecture/pipelines.md)

> `auto_runner.py` 及其测试在当前工作区中处于**已删除但未提交**状态。本文档按仓库 HEAD 描述。

---

## 质量体系

**第一层**：[`style_linter.py`](meta_writing/style_linter.py) —— 13 条行级规则 + 9 条全局计数规则 + 2 条结构规则，纯正则，零成本。抓可枚举的 AI 腔：`那……很……，但……` 脚手架、`不是……是……` 反向下定义、连续单字成段、物体「记得」的拟人化。命中 ERROR 直接阻塞。

**第二层**：三位审稿人各出一张五维评分卡，加权聚合：

| 维度 | 权重 |
|------|------|
| 剧情张力与节奏 | 30% |
| 人物塑造与互动 | 25% |
| 信息量与暗线设计 | 20% |
| 语言与描写质感 | 15% |
| 指令满足与完成度 | 10% |

门槛是双重的：综合分 **≥ 8.0** 且**无任何单维 < 7.0**。只有综合门槛的话，剧情 9.5 分能把人物 5 分背过线——而「人物塌了但剧情爽」正是长篇最致命的失败模式。

修订循环最多 5 轮，且在连续 2 轮提升 < 0.2 分时提前判定停滞退出——修不动就该交回给人，而不是继续烧 token。

调参与维护：[`docs/operations/editorial-scorecard-maintenance.md`](docs/operations/editorial-scorecard-maintenance.md)

---

## 风格档案

同一套引擎按项目切换审美口径，由 `creator_guidance.md` 的关键词自动识别：

| 档案 | 触发关键词 |
|------|-----------|
| `literary_microfeel` 克制微感文学 | 克制美学、微感、留白、纯感官、不解释 |
| `tomato_romance` 番茄快节奏女频 | 番茄、高梗密度、快节奏、爽点、拉扯、女频 |
| `generic` 通用 | （兜底） |

档案不改代码路径，只向五处 system prompt 追加约束，并决定第三编辑用哪套标准。这让「快节奏项目被文学化标准误伤」这类问题在档案层解决，不必动引擎。

---

## 模型供应商

| 供应商 | 用途 | 环境变量 |
|--------|------|---------|
| MiniMax | 手动链路全部角色；自动链路的 StyleAgent | `MINIMAX_API_KEY` |
| DeepSeek | 写手可选；自动链路的结构化抽取 | `DEEPSEEK_API_KEY` |
| Anthropic | 自动链路的编辑角色（缺失则降级） | `ANTHROPIC_API_KEY` |

**密钥只放环境变量或被忽略的 `.env`，绝不写进被跟踪的文件。**

> 手动链路只需 `MINIMAX_API_KEY` 即可完整运行。自动链路缺少 Anthropic/DeepSeek 凭据时会**静默降级**（仅打 WARNING），审稿严格度随之改变——运行时请检查启动日志。

路由细节与配置陷阱：[`docs/architecture/model-routing.md`](docs/architecture/model-routing.md)

---

## 文档

完整索引：[`docs/README.md`](docs/README.md)

| 层 | 内容 |
|----|------|
| [`docs/architecture/`](docs/architecture/) | 总体设计、状态层、智能体层、编排层、模型路由 |
| [`docs/guides/`](docs/guides/) | 快速开始、开新书、手动写作循环、多项目工作区 |
| [`docs/reference/`](docs/reference/) | CLI、Story Bible 字段、配置项、文风规则 |
| [`docs/operations/`](docs/operations/) | 评分体系维护、测试与发布卫生 |
| [`docs/decisions/`](docs/decisions/) | 历史设计决策归档 |

---

## 提交约定

**章节与其 Story Bible 更新必须在同一个提交里。** 只有正文没有状态更新的提交视为不完整。

```powershell
git status --short
python -m pytest -q
rg -n "sk-|API_KEY\s*=|AUTH_TOKEN\s*=|BEGIN .*PRIVATE KEY" .
```

两条链路都会尝试自动 `git commit`，但**失败是静默的**——生成后请 `git log -1 --stat` 确认。

详见 [`docs/operations/testing-and-verification.md`](docs/operations/testing-and-verification.md)
