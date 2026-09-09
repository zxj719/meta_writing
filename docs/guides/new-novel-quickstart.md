# New Novel Quickstart

This is the shortest path to start a new novel in the `meta_writing` workspace, with chapter length around 2000 Chinese characters. Generation runs through whatever agent CLI is available in your environment.

## 1. Create a new project

From the `meta_writing` repo root:

```powershell
meta-writing project create tomato-romance --activate
```

This creates:

```text
novels/tomato-romance/
  story_data/
  chapters/
  creator_guidance.md
  learned_rules.md
  editorial_report.md
```


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

- Set `Target chapter chars` to `2000`
- Set `Minimum chars before expansion` to around `1600`

These values are saved into `story_data/story_core.yaml`, so each novel keeps its own length policy.

## 4. Start writing

```powershell
meta-writing generate --project tomato-romance
```


## 5. Agent availability

No model-provider API key is needed. Generation and review go through the agent CLI in your
environment (Claude Code or Codex), which handles its own authentication.

```powershell
claude -p "reply ok"
python -X utf8 -c "from meta_writing.llm import detect_agent; print(detect_agent().kind)"
```

If `AgentNotFoundError` is raised, put `claude` (or `codex`) on PATH, or set
`META_WRITING_AGENT` / `META_WRITING_AGENT_CMD`. See
[`../reference/configuration.md`](../reference/configuration.md).

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
