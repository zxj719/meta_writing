# MiniMax Writer And Novel Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `meta_writing` support MiniMax as a first-class writer provider and add a repeatable bootstrap path for starting a new novel with per-project chapter length and guidance.

**Architecture:** Store per-novel writing preferences in `StoryCore`, then have both `Orchestrator` and `AutoRunner` derive the writer client and chapter-length policy from those preferences. Scaffold a per-project guidance template plus documentation so a new novel can be started from a single reference brief instead of ad-hoc prompting.

**Tech Stack:** Python 3.12+, Click CLI, Pydantic, pytest, Anthropic-compatible MiniMax client, existing Story Bible YAML persistence

---

### Task 1: Lock The Desired Config Surface In Tests

**Files:**
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\tests\test_writer.py`
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\tests\test_orchestrator.py`
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\tests\test_workspace.py`

- [ ] **Step 1: Write failing tests for writer guidance and per-chapter length**

Add tests that assert:

```python
@pytest.mark.asyncio
async def test_write_prompt_includes_creative_guidance(mock_llm, bible_context):
    writer = WriterAgent(mock_llm)
    await writer.write(
        bible_context=bible_context,
        recent_chapters_text="",
        outline="大纲",
        chapter_number=4,
        creative_guidance="每章约2000字，保持番茄高梗密度。",
    )

    user_msg = mock_llm.complete.call_args.kwargs["messages"][0]["content"]
    assert "创作指导" in user_msg
    assert "每章约2000字" in user_msg
```

```python
@pytest.mark.asyncio
async def test_orchestrator_uses_story_core_chapter_targets(tmp_project):
    orch = Orchestrator(tmp_project, api_key="test")
    orch.writer.write_with_expansion = AsyncMock(
        return_value=WriterResult(
            chapter_text=CHAPTER_TEXT,
            raw_response=_make_response(CHAPTER_TEXT),
        )
    )
```

- [ ] **Step 2: Write failing tests for MiniMax env aliases and project bootstrap files**

Add tests that assert:

```python
def test_create_project_writes_creator_guidance_template(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)
    project_dir = manager.create_project("new-book")

    guidance_path = project_dir / "creator_guidance.md"
    assert guidance_path.is_file()
    assert "小说基本信息" in guidance_path.read_text(encoding="utf-8")
```

```python
def test_anthropic_compatible_client_uses_env_aliases(monkeypatch):
    ...
```

- [ ] **Step 3: Run only the new tests to confirm RED**

Run: `python -m pytest tests/test_writer.py tests/test_orchestrator.py tests/test_workspace.py -q`

Expected: FAIL with missing `creative_guidance`, missing bootstrap file, and missing MiniMax config behavior.

### Task 2: Implement Per-Novel Writing Preferences

**Files:**
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\meta_writing\story_bible\schema.py`
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\meta_writing\cli.py`
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\meta_writing\agents\writer.py`

- [ ] **Step 1: Extend `StoryCore` with writing preference defaults**

Add fields for:

```python
chapter_target_chars: int = Field(default=10000, ge=800)
chapter_min_chars: int = Field(default=7000, ge=500)
writer_provider: str = Field(default="deepseek")
```

- [ ] **Step 2: Ask for these values during `meta-writing init`**

Update interactive init to collect:

```python
writer_provider = Prompt.ask(
    "Writer 模型提供方",
    choices=["deepseek", "minimax"],
    default="minimax",
)
chapter_target_chars = IntPrompt.ask("目标单章字数", default=2000)
default_min_chars = max(800, int(chapter_target_chars * 0.8))
chapter_min_chars = IntPrompt.ask("触发扩写的最低字数", default=default_min_chars)
```

- [ ] **Step 3: Pass creative guidance and chapter targets into `WriterAgent`**

Update signatures:

```python
async def write(..., creative_guidance: str = "") -> WriterResult:
async def write_with_expansion(..., creative_guidance: str = "", min_chars: int = MIN_CHAPTER_CHARS, target_chars: int = TARGET_CHAPTER_CHARS) -> WriterResult:
async def expand(..., creative_guidance: str = "", target_chars: int = TARGET_CHAPTER_CHARS) -> WriterResult:
```

- [ ] **Step 4: Re-run focused tests to confirm GREEN**

Run: `python -m pytest tests/test_writer.py tests/test_story_bible.py -q`

Expected: PASS

### Task 3: Make MiniMax A Real Writer Provider

**Files:**
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\meta_writing\llm.py`
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\auto_runner.py`
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\meta_writing\orchestrator.py`

- [ ] **Step 1: Support Anthropic-compatible MiniMax env aliases**

Make the MiniMax client accept either:

```python
os.environ.get("MINIMAX_API_KEY")
os.environ.get("ANTHROPIC_AUTH_TOKEN")
```

and base URL from either:

```python
os.environ.get("MINIMAX_BASE_URL", MINIMAX_BASE_URL)
os.environ.get("ANTHROPIC_BASE_URL", MINIMAX_BASE_URL)
```

- [ ] **Step 2: Add a small writer-provider factory**

Implement a pure helper such as:

```python
def build_writer_client(provider: str, minimax_api_key: str = "") -> tuple[object, str]:
    if provider == "minimax":
        return LLMClient(api_key=minimax_api_key or None), MODEL_SONNET
    return DeepSeekClient(), MODEL_DEEPSEEK_CHAT
```

- [ ] **Step 3: Use that factory in `AutoRunner` and `Orchestrator`**

`AutoRunner` should resolve the provider from:
1. explicit CLI override if provided
2. `bible.core.writer_provider`
3. fallback `"deepseek"`

`Orchestrator` should resolve from:
1. explicit constructor arg if provided
2. `bible.core.writer_provider`
3. fallback `"minimax"` when using `LLMClient` directly

- [ ] **Step 4: Re-run focused tests to confirm GREEN**

Run: `python -m pytest tests/test_orchestrator.py tests/test_writer.py tests/test_workspace.py -q`

Expected: PASS

### Task 4: Bootstrap New Novel Creation

**Files:**
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\meta_writing\workspace.py`
- Add: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\docs\new-novel-quickstart.md`

- [ ] **Step 1: Scaffold `creator_guidance.md` for each new project**

Create a template containing sections like:

```markdown
# Creator Guidance

## 小说基本信息
- 书名:
- 题材:
- 平台风格:

## 已有章节摘要

## 当前人物状态

## 阶段大纲

## 写作要求
- 目标单章字数:
- 每章至少一个笑点/爽点:
- 结尾钩子:
```

- [ ] **Step 2: Document the exact startup flow**

Add a quickstart doc showing:

```powershell
meta-writing project create tomato-romance --activate
meta-writing init --project tomato-romance
meta-writing generate --project tomato-romance --guidance "$(Get-Content .\\novels\\tomato-romance\\creator_guidance.md -Raw)"
python auto_runner.py --project tomato-romance --writer-provider minimax --workspace-dir .
```

- [ ] **Step 3: Run bootstrap-related tests**

Run: `python -m pytest tests/test_workspace.py -q`

Expected: PASS

### Task 5: Full Verification

**Files:**
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\tests\conftest.py` (only if fixtures need updates)
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\tests\test_story_bible.py` (only if new defaults need coverage)

- [ ] **Step 1: Run the full suite**

Run: `python -m pytest tests -q`

Expected: PASS with zero failures.

- [ ] **Step 2: Check CLI help for new provider-related options if added**

Run: `meta-writing --help`
Run: `python auto_runner.py --help`

Expected: new options visible and descriptions sensible.
