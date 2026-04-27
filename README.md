# Meta Writing

`meta_writing` is a local-first Chinese web novel generation workspace. It combines a Story Bible, project isolation, multi-agent review, style linting, and optional autonomous generation so one novel does not accidentally inherit another novel's state.

The current priority is practical long-form writing: keep plot momentum, update story state after every chapter, and make future chapter generation easier to continue without context leakage.

## What This Repository Contains

- `meta_writing/`: Python package for the CLI, orchestration, agents, Story Bible loading, style linting, and workspace management.
- `auto_runner.py`: autonomous chapter loop for projects that explicitly opt into `automatic` workflow mode.
- `novels/`: isolated novel projects. Each project owns its own chapters, Story Bible, guidance, learned rules, and workflow metadata.
- `docs/`: maintenance notes for multi-project workflow, new-novel startup, and the editorial scorecard.
- `tests/`: pytest coverage for workspace isolation, orchestrator behavior, writer routing, style linting, and editorial scoring.

## Core Concepts

### Project Isolation

Every novel should live under `novels/<project-name>/`.

Important project files:

- `.meta-writing-project.json`: project name and workflow mode.
- `creator_guidance.md`: long-lived author instructions for this novel.
- `learned_rules.md`: accumulated style and continuity rules.
- `chapters/`: generated chapter markdown files.
- `story_data/`: Story Bible YAML files, including characters, chapter summaries, timeline, pacing, and foreshadowing.
- `auto_runner_log.md`: automatic-mode execution notes when relevant.
- `editorial_reviews/`: structured editorial review traces when the scorecard loop is used.

The active project can also be recorded in `.meta-writing/workspace.json`.

### Manual Mode vs Automatic Mode

There are two supported workflow modes:

- `manual`: chapter writing is directed by the human/Codex session. After each chapter, update story state manually and run verification. This is the recommended mode for quality-sensitive novels.
- `automatic`: `auto_runner.py` can plan, write, review, revise, update state, and optionally push. Use this only for projects that are explicitly configured for automatic workflow.

`rescue-male-lead` is currently a manual-mode project. Do not use `auto_runner.py` to overwrite its chapter text unless the workflow mode is intentionally changed.

### Editorial Review

The quality gate uses a five-part scorecard:

- Plot tension and pacing, weight 30%.
- Character shaping and interaction, weight 25%.
- Information design and hidden-line handling, weight 20%.
- Language and descriptive texture, weight 15%.
- Instruction fit and completion, weight 10%.

The default pass threshold is `8.0`. The scoring system is documented in `docs/editorial-scorecard-maintenance.md`.

### Style Linting

`meta_writing/style_linter.py` catches common AI-flavored prose issues, including repeated scaffolds, hard sentence fragmentation, overused judgement patterns, and project-specific banned openings.

Current high-priority style constraints include:

- Avoid repeated `那……很……，但……` and `那……不……，但……` sentence scaffolds.
- Avoid opening a chapter with `……一……，就……`.
- Reduce mechanical `不是……是……` explanation pairs unless they are natural dialogue.
- Prefer action, expression, environment, and object details over authorial explanation.

## Setup

Use Python 3.12 or newer.

```powershell
cd C:\Users\xingj\Documents\agent\novel_generator\meta_writing
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

If you use vector retrieval features, install any model/runtime dependencies required by `chromadb` and `sentence-transformers`.

## LLM Configuration

Do not commit real API keys. Put keys in your shell environment or a local ignored `.env` file.

Supported writer providers:

- `minimax`
- `deepseek`

Common environment variables:

```powershell
$env:MINIMAX_API_KEY = "..."
$env:MINIMAX_BASE_URL = "https://api.minimaxi.com/anthropic"
$env:DEEPSEEK_API_KEY = "..."
$env:ANTHROPIC_API_KEY = "..."
```

Compatibility aliases supported by the MiniMax client:

```powershell
$env:ANTHROPIC_AUTH_TOKEN = "..."
$env:ANTHROPIC_BASE_URL = "https://api.minimaxi.com/anthropic"
```

Use environment variables only; never paste a live token into tracked files.

## Common Commands

Show known projects:

```powershell
python -m meta_writing.cli --workspace-dir . project list
```

Set the active project:

```powershell
python -m meta_writing.cli --workspace-dir . project use rescue-male-lead
```

Check the active project:

```powershell
python -m meta_writing.cli --workspace-dir . project current
```

Show Story Bible status:

```powershell
python -m meta_writing.cli --workspace-dir . --project rescue-male-lead status
```

Generate through the manual CLI pipeline:

```powershell
python -m meta_writing.cli --workspace-dir . --project rescue-male-lead generate --guidance "继续下一章，写完后更新角色状态、伏笔、时间线和节奏。"
```

Run automatic mode for an automatic project:

```powershell
python auto_runner.py --project <project-name> --from 1 --to 10
```

Dry-run automatic planning without writing:

```powershell
python auto_runner.py --project <project-name> --to 10 --dry-run
```

## Starting a New Novel

Create a new isolated project:

```powershell
python -m meta_writing.cli --workspace-dir . project create my-new-novel --mode manual --activate
```

Then fill in:

- `novels/my-new-novel/creator_guidance.md`
- `novels/my-new-novel/story_data/story_core.yaml`
- initial character cards under `novels/my-new-novel/story_data/characters/`

Recommended startup checklist:

- Define title, genre, platform style, target chapter length, and core reader satisfaction.
- Write the first-stage outline and the next 5-10 chapter direction.
- Define protagonist, love interest or major counterpart, first antagonist, and at least one reusable side character.
- Add hard style rules early, especially banned sentence patterns and dialogue texture preferences.
- Decide whether the project is `manual` or `automatic`; do not mix modes casually.

For a longer walkthrough, see `docs/new-novel-quickstart.md`.

## Manual Chapter Workflow

For quality-sensitive novels, use this loop:

1. Read the last chapter, `creator_guidance.md`, `learned_rules.md`, and relevant Story Bible files.
2. Write the next chapter in `chapters/<number>.md`.
3. Run style checks and remove mechanical patterns before accepting the chapter.
4. Update `story_data/chapter_summaries/<number>.yaml`.
5. Update character cards for every changed character.
6. Update timeline, pacing, and foreshadowing.
7. Re-load the Story Bible to verify schema consistency.
8. Record any new reusable writing rule in `learned_rules.md` or `creator_guidance.md`.

This is the current preferred flow for `rescue-male-lead`.

## Verification

Run the full test suite:

```powershell
python -m pytest -q
```

Run the style linter tests only:

```powershell
python -m pytest tests\test_style_linter.py -q
```

Load a project's Story Bible from PowerShell:

```powershell
@'
from pathlib import Path
from meta_writing.story_bible.loader import StoryBibleLoader
root = Path("novels/rescue-male-lead/story_data")
bible = StoryBibleLoader(root).load()
print("current_chapter=", bible.core.current_chapter)
print("characters=", len(bible.characters))
print("chapter_summaries=", len(bible.chapter_summaries))
'@ | python -X utf8 -
```

## Git Hygiene

Before pushing:

```powershell
git status --short
python -m pytest -q
git diff --check
```

Also scan for accidental secrets:

```powershell
rg -n "sk-|API_KEY\\s*=|AUTH_TOKEN\\s*=|BEGIN .*PRIVATE KEY" .
```

Commit and push:

```powershell
git add .
git commit -m "docs: add project README"
git push origin master
```

If generated chapters are part of the intended release, commit the chapter files and their Story Bible updates together. A chapter without its state update is considered incomplete.

## Current Notes

- `rescue-male-lead` has moved into a manual, quality-controlled chapter workflow.
- `auto_runner.py` remains useful for automatic projects and tooling experiments, but it should not be allowed to cross-contaminate manual projects.
- The README documents workflow and safe operation. Novel-specific creative direction belongs in each project's `creator_guidance.md` and `learned_rules.md`.
