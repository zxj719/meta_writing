# TODOS

## Post-MVP: 30-Chapter Stress Test
**What:** After the 10-chapter smoke test passes, run a 30-chapter arc to validate long-range consistency, foreshadowing aging, and Story Bible extraction drift.
**Why:** 10 chapters fits in one context window — it doesn't stress-test the architecture. 30 chapters forces the system past context limits and exposes accumulated extraction errors.
**Depends on:** 10-chapter MVP passing.
**Estimated cost:** ~$100-150 in API calls, ~1 day.

## Post-MVP: Style Agent + Theme Agent
**What:** Implement Style Agent (pacing, hooks, AI slop detection) and Theme Agent (thematic coherence, character arc tracking).
**Why:** Deferred from MVP to focus on core consistency (Continuity Agent). These agents add quality polish.
**Depends on:** 30-chapter stress test passing.
**Context:** Design doc has full specs for both agents including methodology mapping.

## Post-MVP: Evaluate DeepSeek/Qwen as Writer Agent
**What:** Benchmark DeepSeek-V3 and Qwen-2.5 as Writer Agent alternatives. Compare Chinese prose quality, consistency, and cost.
**Why:** Could reduce per-novel cost from ~$300-500 to $50-100 range. Chinese-native models may produce equal or better Chinese prose.
**Depends on:** MVP working with Claude Sonnet.
**Context:** Open Question #1 in the design doc.
