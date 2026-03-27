# Claude Configuration

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
