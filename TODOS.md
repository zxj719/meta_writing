# TODOS

## ✅ Done: Style Agent
**What:** Implemented LLM-based Style Agent (`meta_writing/agents/style.py`) using MiniMax-M2.7.
Checks: AI verbal tics, structural echoes with previous chapters, over-explanation of sensing,
dialogue meta-commentary, paragraph rhythm monotony.
**Wired into:** Orchestrator review+revise loop (alongside Continuity Agent).

## Post-MVP: 30-Chapter Stress Test
**What:** After the 10-chapter smoke test passes, run a 30-chapter arc to validate long-range consistency, foreshadowing aging, and Story Bible extraction drift.
**Why:** 10 chapters fits in one context window — it doesn't stress-test the architecture. 30 chapters forces the system past context limits and exposes accumulated extraction errors.
**Depends on:** 10-chapter MVP passing. ✅ (ch1-10 complete 2026-03-29)
**Estimated cost:** ~$100-150 in API calls, ~1 day.

## Post-MVP: Theme Agent
**What:** Implement Theme Agent (thematic coherence, character arc tracking).
**Why:** Deferred from MVP. Tracks thematic through-lines and character arc progression over many chapters. Different from Style Agent (which is per-chapter prose quality).
**Depends on:** 30-chapter stress test.
**Context:** Style Agent is done. Theme Agent is the remaining piece from the original plan.

## Post-MVP: Evaluate DeepSeek/Qwen as Writer Agent
**What:** Benchmark DeepSeek-V3 and Qwen-2.5 as Writer Agent alternatives.
**Why:** Could reduce per-novel cost. MiniMax-M2.7 is current backbone — Chinese-native alternatives worth evaluating.
**Note:** System already uses MiniMax (not Claude) as the generation backbone. DeepSeek/Qwen comparison is still valid.
**Depends on:** MVP working. ✅ (10-chapter MVP complete)
