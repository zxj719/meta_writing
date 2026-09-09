# 快速开始

从零把 `meta_writing` 跑起来。全程本地，不需要任何服务端、部署或网络服务——只需要一个 Python 环境和一个已登录的智能体 CLI。

---

## 1. 环境要求

- Python **3.12+**
- git（章节落盘时会自动 commit）
- 一个已登录的智能体 CLI：Claude Code（`claude`）或 Codex（`codex`）
- **不需要**任何模型供应商的 API key

---

## 2. 安装

```powershell
cd <仓库路径>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Linux / macOS：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

安装后 `meta-writing` 命令可用。也可以始终用 `python -m meta_writing.cli` 免安装调用。

> 使用向量检索（当前无调用方）需要额外安装 `chromadb` 与 `sentence-transformers` 的模型运行时依赖。BGE-M3 约需 2.2GB 显存。

---

## 3. 准备智能体

系统**不需要任何模型供应商的 API key**。它会子进程调用你环境里的智能体 CLI（Claude Code 或 Codex），认证由该 CLI 自己负责。

确认智能体可用且已登录：

```powershell
claude -p "回复 ok"
```

若提示 `Not logged in`，先在交互式 `claude` 里跑 `/login`。

确认 `meta_writing` 能解析到它：

```powershell
python -X utf8 -c "from meta_writing.llm import detect_agent; s=detect_agent(); print(s.kind, s.argv)"
```

预期打印 `claude ('.../claude.EXE',)`。若抛 `AgentNotFoundError`，按错误信息里的三种方式之一配置——最省事的是把 `claude` 放上 PATH。

需要指定别的智能体时：

```powershell
$env:META_WRITING_AGENT = "codex"                        # 用 codex
$env:META_WRITING_AGENT_CMD = "/opt/my-agent --flag"     # 完全自定义
```

完整变量表见 [`../reference/configuration.md`](../reference/configuration.md)。

> **成本提示**：每次调用有约 11.7K input token 的固定开销（CLI 启动与上下文加载），与提示词长短基本无关。一章最坏约 20 次调用。

---

## 4. 跑通测试

在写第一章之前先确认环境正常。全部 LLM 调用在单元测试中都被 mock，不消耗额度：

```powershell
python -m pytest -q
```

---

## 5. 创建第一个项目

```powershell
meta-writing --workspace-dir . project create my-first-novel --activate
```

生成的结构：

```
novels/my-first-novel/
├── .meta-writing-project.json    {"name": "my-first-novel"}
├── creator_guidance.md           模板，待填写
├── story_data/                   空
└── chapters/                     空
```

确认：

```powershell
meta-writing --workspace-dir . project list
```

---

## 6. 初始化故事核心

```powershell
meta-writing --workspace-dir . --project my-first-novel init
```

交互式创建 `story_data/story_core.yaml`。逐项说明见 [`../reference/cli.md`](../reference/cli.md)。

**两个建议现在就填对，后面改起来麻烦**：

| 提问 | 建议 |
|------|------|
| Target chapter chars | 按平台习惯填（如 2000）。留空会落到 10000 字的兜底值 |
| Minimum chars before expansion | 目标的 80% 左右。低于此值会自动扩写一次 |

言情项目请注意：`init` 的伏笔寿命默认值查表命不中 `现代言情`/`古代言情`，会给 20 而非 15。需要 15 请在提问时直接输入，或事后改 `story_core.yaml` 的 `foreshadowing_max_age_chapters`。

---

## 7. 填写创作指导

`novels/my-first-novel/creator_guidance.md` 是全流程最重要的人工输入——它被合并进**每一个** agent 的提示词，并决定风格档案的自动识别。

模板已包含小说基本信息、已写章节摘要、当前人物状态、阶段大纲、写作要求五个小节。

**风格档案由这个文件的关键词决定**（见 [`../reference/configuration.md`](../reference/configuration.md)）：

- 写了「克制美学」「微感」「留白」「纯感官」等 → `literary_microfeel`
- 写了「番茄」「快节奏」「爽点」「女频」「拉扯」等 → `tomato_romance`
- 都没有 → `generic`

档案会改变 Planner/Writer/审稿的口径，以及第三编辑用哪套标准。**如果你的项目是快节奏网文，务必在这里写明**，否则会被通用标准（甚至文学化标准）评判。

至少填这几项再开始写：书名、题材、平台风格、目标单章字数、禁止出现的套路句式。

---

## 8. 添加角色

```powershell
meta-writing --workspace-dir . --project my-first-novel add-character
```

`core_triangle`（欲望/能力/阻碍）与 `motivation_type` 是**必填**——这两项缺失会导致整本 Story Bible 加载失败。其余字段（关系、知识状态、隐藏背景）需手工编辑 `story_data/characters/<name>.yaml` 补充。

至少建好：主角、主要对手方、一个可复用配角。

---

## 9. 生成第一章

```powershell
meta-writing --workspace-dir . --project my-first-novel generate --guidance "第一章：建立主角处境与核心矛盾，结尾留钩子。"
```

流程中会停三次等你决策：

1. **选分支** — Planner 给 2-3 条走向，看大纲/爽点级别/钩子类型/风险等级选一条
2. **审章节** — `approve` 接受 / `edit` 用你输入的文本**整体替换**正文 / `reject` 放弃本章
3. **确认状态变更** — 是否把检出的角色状态变化写回 Story Bible

在你 `approve` 之前，审稿-修订循环最多已经自动跑了 5 轮。

---

## 10. 检查产出

```powershell
meta-writing --workspace-dir . --project my-first-novel status
```

以及：

| 路径 | 内容 |
|------|------|
| `chapters/001.md` | 正文 |
| `editorial_reviews/001.md` | 审稿留痕，人读 |
| `editorial_reviews/001.json` | 审稿留痕，机读 |

**先看 `editorial_reviews/001.md` 的 `final_decision`**：

| 取值 | 含义 |
|------|------|
| `passed` | 全部闸门通过 |
| `stalled_below_threshold` | 修不动了，**带着已知问题落盘** |
| `max_revisions_reached` | 跑满 5 轮仍未达标，**带着已知问题落盘** |

后两者需要人工介入。

章节会被自动 `git commit`。**但 git 失败是静默的**——确认一下：

```powershell
git log -1 --stat
```

---

## 11. 接下来

| 目标 | 文档 |
|------|------|
| 理解系统怎么运作 | [`../architecture/overview.md`](../architecture/overview.md) |
| 长期写作的推荐循环 | [`manual-chapter-workflow.md`](manual-chapter-workflow.md) |
| 更完整的开书清单 | [`new-novel-quickstart.md`](new-novel-quickstart.md) |
| 同时写多本书 | [`multi-project-workspace.md`](multi-project-workspace.md) |
| 质量不满意，想调标准 | [`../operations/editorial-scorecard-maintenance.md`](../operations/editorial-scorecard-maintenance.md) |
