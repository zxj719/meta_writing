# New Novel Quickstart

This is the shortest path to start a new novel in the `meta_writing` workspace with MiniMax as the writer and chapter length around 2000 Chinese characters.

## 1. Create a new project

From the `meta_writing` repo root:

```powershell
meta-writing project create tomato-romance --mode manual --activate
```

This creates:

```text
novels/tomato-romance/
  story_data/
  chapters/
  creator_guidance.md
  learned_rules.md
  auto_runner_log.md
  editorial_report.md
```

Use `--mode manual` for the interactive first-five-chapter style workflow.
Use `--mode automatic` only when you want `auto_runner.py` to own planning, draft, review, and revision.

## 2. Fill in the project brief

Edit:

```text
novels/tomato-romance/creator_guidance.md
```

Recommended structure:

- 小说基本信息
- 已写章节摘要
- 当前人物状态
- 阶段大纲
- 写作要求

For a Tomato-style urban romance/system novel, put your reference material there instead of feeding a giant prompt every time.

Example guidance points:

```markdown
## 小说基本信息
- 书名：偏执男主别黑化，你的救赎来了
- 题材：都市 + 重生 + 系统 + 救赎偏执男主
- 平台风格：高梗密度、快节奏、强情绪、轻松吐槽

## 写作要求
- 目标单章字数：2000
- 每章至少一个笑点或爽点
- 男女主互动要有拉扯感
- 每章结尾必须留钩子
```

## 3. Initialize the Story Bible

```powershell
meta-writing init --project tomato-romance
```

During init:

- Set `Writer provider` to `minimax`
- Set `Target chapter chars` to `2000`
- Set `Minimum chars before expansion` to around `1600`

These values are saved into `story_data/story_core.yaml`, so each novel keeps its own writer and length policy.

## 4. Start writing

Interactive pipeline:

```powershell
meta-writing generate --project tomato-romance
```

`meta-writing generate` only works on `manual` projects.

Autonomous pipeline:

```powershell
python auto_runner.py --project tomato-romance --workspace-dir .
```

`auto_runner.py` only works on `automatic` projects. If you want that path, create the project with `--mode automatic` or switch the project mode later:

```powershell
meta-writing project mode automatic --name tomato-romance
```

If you want to force MiniMax for one run:

```powershell
python auto_runner.py --project tomato-romance --workspace-dir . --writer-provider minimax
```

## 5. MiniMax auth

Either set the dedicated MiniMax variable:

```powershell
$env:MINIMAX_API_KEY = "..."
```

Or use the Anthropic-compatible aliases:

```powershell
$env:ANTHROPIC_BASE_URL = "https://api.minimaxi.com/anthropic"
$env:ANTHROPIC_AUTH_TOKEN = "..."
```

Do not commit real tokens into the repo.

## 6. Recommended workflow for your reference format

Use `creator_guidance.md` for the long-form reference content you pasted in this chat:

- 小说基本信息
- 已写好的前三章摘要
- 当前人物状态
- 完整阶段大纲
- 写作任务和每章要求

Keep `story_core.yaml` for durable structured state.
Keep `creator_guidance.md` for style, platform targeting, phase goals, and chapter-level instructions.

## 7. Keep old root novels out of the workspace root

If the repo root still has a previous novel under `story_data/` and `chapters/`, migrate it before starting another one:

```powershell
meta-writing project migrate-root legacy-book --no-activate
```

After that, all novels live under `novels/<project>/`, and the workspace will no longer mix root-level story files into new projects.
