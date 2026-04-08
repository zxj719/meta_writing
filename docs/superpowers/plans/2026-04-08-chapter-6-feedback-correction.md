# Chapter 6 Feedback Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Encode the user's Chapter 6 editorial feedback into project memory, rerun `auto_runner.py` for Chapter 6, and verify the regenerated draft aligns better with Chapters 3-5.

**Architecture:** Reuse the existing `auto_runner` self-correction inputs instead of adding a new subsystem. Persist immediate correction pressure in `.auto_runner_correction.json`, persist durable style rules in `learned_rules.md`, then regenerate Chapter 6 in-place via the project-level AutoRunner.

**Tech Stack:** Python, `meta_writing` AutoRunner, project YAML/Markdown state files, pytest-free runtime verification for generated content.

---

### Task 1: Persist Human Feedback As Next-Run Correction

**Files:**
- Create: `novels/rescue-male-lead/.auto_runner_correction.json`
- Modify: `novels/rescue-male-lead/learned_rules.md`

- [ ] **Step 1: Write the one-shot correction payload**

Write a JSON payload that captures the user’s Chapter 6 concerns:

```json
{
  "chapter_number": 6,
  "issues_summary": "第6章存在三类偏移：沈清辞台词过于金句化，系统话痨并抢戏，同章并置过多推进点导致情感场被打断。",
  "new_lessons": [
    "沈清辞台词回到前三到五章的碎、生活化表达，不连续输出结论句。",
    "系统保持低频吐槽和面板提示，不抢主角对话，不密集人格化输出。",
    "单章只保留一到两个主要推进点，避免情感坦白、系统暴露、八卦插入和新伏笔同时堆叠。",
    "避免高密度“是，不是”口癖和连续断言句。",
    "重生信息只能侧面暗示，第6章不要直接坦白“我先回来了”。"
  ]
}
```

- [ ] **Step 2: Append durable style rules to project memory**

Append a dated section to `novels/rescue-male-lead/learned_rules.md` that restates the same constraints as long-term novel-specific rules.

- [ ] **Step 3: Verify the files were written**

Run:

```powershell
Get-Content novels\rescue-male-lead\.auto_runner_correction.json
Get-Content novels\rescue-male-lead\learned_rules.md | Select-Object -Last 30
```

Expected: The JSON file exists and the new dated rules appear at the end of `learned_rules.md`.

### Task 2: Regenerate Chapter 6 Through AutoRunner

**Files:**
- Modify: `novels/rescue-male-lead/chapters/006.md`
- Modify: `novels/rescue-male-lead/story_data/chapter_summaries/006.yaml`
- Modify: `novels/rescue-male-lead/story_data/story_core.yaml`

- [ ] **Step 1: Run AutoRunner against Chapter 6 only**

Run:

```powershell
$env:ANTHROPIC_BASE_URL="https://api.minimaxi.com/anthropic"
$env:ANTHROPIC_AUTH_TOKEN="<MiniMax token>"
python auto_runner.py --project rescue-male-lead --workspace-dir . --from 6 --to 6 --writer-provider minimax
```

Expected: AutoRunner rewrites Chapter 6, updates the Story Bible, and logs a completed Chapter 6 run.

- [ ] **Step 2: Verify Chapter 6 changed**

Run:

```powershell
git diff -- novels/rescue-male-lead/chapters/006.md novels/rescue-male-lead/story_data/chapter_summaries/006.yaml novels/rescue-male-lead/story_data/story_core.yaml
```

Expected: The regenerated chapter and its summary differ from the previous draft.

### Task 3: Verify The New Draft Against The Feedback

**Files:**
- Inspect: `novels/rescue-male-lead/chapters/006.md`

- [ ] **Step 1: Inspect the regenerated chapter**

Read the opening, the corridor emotional scene, and the chapter ending. Confirm:

```text
1. Shen Qingci's dialogue is more fragmented and conversational.
2. System presence is lower and does not dominate the scene.
3. The chapter keeps the emotional core but reduces simultaneous subplot stacking.
```

- [ ] **Step 2: Capture simple objective checks**

Run:

```powershell
@'
from pathlib import Path
text = Path("novels/rescue-male-lead/chapters/006.md").read_text(encoding="utf-8")
print("chars", len(text))
print("system_panels", text.count("【"))
print("system_word", text.count("系统"))
print("shi_phrase", text.count("是，不是"))
'@ | python -
```

Expected: The regenerated chapter does not show a spike in system markers, and the obvious repeated口癖 check stays low.

- [ ] **Step 3: If still off, rerun with a tighter correction summary**

If the regenerated chapter still overstates or over-stacks, rewrite `.auto_runner_correction.json` with sharper wording and rerun Task 2 once more instead of hand-editing the chapter.
