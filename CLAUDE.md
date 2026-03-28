# Claude Configuration

## Project: meta_writing

Multi-agent Chinese web novel generation system. 3 MVP agents (Planner + Writer + Continuity) with shared Story Bible memory layer.

### Architecture

- `meta_writing/llm.py` — Anthropic API wrapper with retry logic
- `meta_writing/orchestrator.py` — Pipeline controller (plan → write → review → commit)
- `meta_writing/agents/` — Planner (Opus), Writer (Sonnet), Continuity (Sonnet)
- `meta_writing/story_bible/` — Schema (Pydantic), Loader (YAML), Compressor (context budget)
- `meta_writing/vector_store/` — ChromaDB + BGE-M3 for semantic chapter retrieval
- `meta_writing/cli.py` — Rich CLI (init, generate, status, add-character)
- `story_data/` — Story Bible YAML files (git-tracked)
- `chapters/` — Generated chapter text (git-tracked)

### Testing

- Run: `python -m pytest tests/ -v`
- Framework: pytest + pytest-asyncio
- All LLM calls are mocked in unit tests
- Integration tests (real LLM): `python -m pytest -m integration`
- 47 unit tests covering schema validation, YAML round-trip, compression tiers, agent response parsing, orchestrator pipeline, and chunk splitting

### Key Commands

```bash
# Activate venv
source .venv/Scripts/activate

# Run CLI
meta-writing init              # Initialize a new story
meta-writing generate          # Generate next chapter
meta-writing status            # Show Story Bible status
meta-writing add-character     # Add a character
```

## gstack

For all web browsing tasks, use the `/browse` skill from gstack. Never use `mcp__claude-in-chrome__*` tools.

### Available Skills

- `/office-hours` - Office hours consultations
- `/plan-ceo-review` - CEO-level plan review
- `/plan-eng-review` - Engineering plan review
- `/plan-design-review` - Design plan review
- `/design-consultation` - Design consultation sessions
- `/review` - Code review
- `/ship` - Ship and deployment workflow
- `/land-and-deploy` - Land and deploy changes
- `/canary` - Canary deployment management
- `/benchmark` - Performance benchmarking
- `/browse` - Web browsing (use this instead of mcp__claude-in-chrome__* tools)
- `/qa` - Quality assurance testing
- `/qa-only` - QA-only workflow
- `/design-review` - Design review sessions
- `/setup-browser-cookies` - Browser cookie setup
- `/setup-deploy` - Deployment setup
- `/retro` - Retrospective sessions
- `/investigate` - Investigation and debugging
- `/document-release` - Release documentation
- `/codex` - Code documentation
- `/cso` - Chief Security Officer workflows
- `/autoplan` - Automated planning
- `/careful` - Careful mode for sensitive operations
- `/freeze` - Freeze changes
- `/guard` - Guard mode
- `/unfreeze` - Unfreeze changes
- `/gstack-upgrade` - Upgrade gstack

### Troubleshooting

If gstack skills aren't working, rebuild the binary and re-register skills by running:

```
cd .claude/skills/gstack && ./setup
```
