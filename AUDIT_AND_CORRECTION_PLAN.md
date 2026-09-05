# Debate Arena — Audit & Correction Plan

## 1. Architecture map (as found)

```
User Topic
  -> arena/graph.py (LangGraph StateGraph, DebateState)
     -> moderator_node            (arena/agents.py)
     -> {elena,marcus}_tools      (arena/agents.py:tool_node)
            -> research_planner.ResearchPlanner.create_plan   (arena/research_planner.py)
            -> tools: web_search / search_documents / query_dataset /
               execute_math / simulate_growth                 (arena/tools.py)
     -> {elena,marcus}_strategy   (arena/agents.py:strategy_node)
     -> {elena,marcus}            (arena/agents.py:agent_node -> prompts.build_agent_prompt)
     -> verify                    (arena/agents.py:verify_node -> evidence.run_combined_assessment)
     -> contradiction_check       (arena/agents.py:contradiction_node)
     -> score                     (arena/agents.py:score_node -> momentum.compute_momentum)
     -> [loop until max_turns] -> summary (arena/agents.py:summary_node)
  -> persistence.py (autosave JSON per debate)
  -> server.py (FastAPI) / main.py (Rich CLI) both drive the same graph.invoke() loop
  -> frontend/src (React: DebateContainer, DebateChat, DebateStats, Sidebar)
```

Files responsible for each stage:

| Stage | File / function |
|---|---|
| Agent identity & symmetry | `arena/prompts.py` (`build_agent_prompt`, `ELENA`/`MARCUS`) |
| Evidence retrieval (web + RAG) | `arena/research_planner.py`, `arena/tools.py` (`web_search`, `search_documents`) |
| Claim verification, citation quality, AI Judge, contradiction (1 LLM call) | `arena/evidence.py` (`run_combined_assessment`) |
| Contradiction bookkeeping | `arena/agents.py` (`contradiction_node`), `arena/contradiction.py` (standalone checker, currently unused by the graph but kept/tested) |
| Rule-based Activity/Momentum score | `arena/momentum.py` |
| Weighted composite + cumulative + winner | `arena/agents.py` (`score_node`) |
| Final narrative summary | `arena/agents.py` (`summary_node`) |
| Frontend scoreboard | `frontend/src/components/DebateStats.jsx` |

## 2. What the codebase already gets right (verified, left alone)

- **Agent symmetry (Core Problem #4):** `prompts.py`'s `build_agent_prompt` is a single shared template; Elena/Marcus differ only in the `stance` block ("always oppose" / "always support"), which is structurally symmetric. `research_planner.py` builds parallel query sets ("arguments against X" / "arguments supporting X") with identical shapes. `phases.py` gives both sides the same phase instructions. **No asymmetric task difficulty found.**
- **Weighted composite formula (Core Problem #11):** `score_node` computes `0.35*grounding + 0.25*rebuttal*10 + 0.20*logic*10 + 0.10*engagement_0_100 + 0.10*clarity*10` — every term is pre-scaled to 0-100 before weighting, weights sum to 1.0, and nothing is double-counted. This was already correct.
- **Activity score isolation (Core Problem #10):** verbosity/tool-use/number-count are computed in `momentum.py` but were *already* demoted to "informational only" — only the deterministic lexical-overlap `engagement` term (capped at 10) feeds the winner-deciding composite, at a 10% weight. Verbosity/tool-use/numeric-count cannot swing the winner today.
- **Schema propagation:** `state.py` already documents and fixes a real prior bug (LangGraph silently drops any key a node returns that isn't declared in the `DebateState` TypedDict). Any new field added below must be declared there — done in section 4.
- **Contradiction detector already understands qualifiers** ("some" vs "all", "eventually" vs "currently") per its prompt — reasonable as-is.

## 3. Confirmed gaps, with severity

| # | Problem | Root cause | Severity |
|---|---|---|---|
| 1 | Claim vs. evidence conflation (#1) | `_COMBINED_PROMPT` in `evidence.py` only asked for a flat SUPPORTED/PARTIALLY/UNSUPPORTED verdict per claim, with **no** check for whether the speaker stacked an unsupported inference on top of a genuinely supported fact, and `grounding_score` was a single **unaudited LLM guess**, not derived from the verdicts it just produced. | **CRITICAL** |
| 2 | Rebuttal quality not actually measuring engagement (#2) | `rebuttal` was a bare 1-10 LLM number judged on "argument quality alone" — a well-written non-sequitur could score as high as a direct rebuttal. | **CRITICAL** |
| 3 | Source credibility is 100% subjective (#6) | `citation_credibility` was an LLM guess with no rule-based grounding; a LinkedIn post and a peer-reviewed paper could get the same 9/10 with no structural check. | **CRITICAL** |
| 4 | Evidence retrieval is topic-level, not claim-level (#5) | `research_planner.create_plan` builds queries from the debate topic only (`"arguments against {topic}"`); it ignores the opponent's actual last claim, so mid-debate rebuttal turns don't fetch evidence targeted at what was just said. | **HIGH** |
| 5 | Contradictions and overclaims are tracked but never penalized in scoring (#8/#9 interaction with #11) | `contradiction_node` records contradictions; `score_node` never reads them. A contradiction currently costs nothing. | **HIGH** |
| 6 | No winner confidence / "too close to call" (#12) | `summary_node` always names a winner from `max(weighted_scores, ...)`, with no margin-relative confidence banding. | **HIGH** |
| 7 | Judge fairness instructions incomplete (#3) | The combined prompt scores rebuttal/logic/clarity but never explicitly tells the model to ignore stance, tone, or agent identity, or to avoid penalizing a well-reasoned concession. | **MEDIUM** |
| 8 | Frontend shows aggregate numbers only (#14) | `DebateStats.jsx` shows composite/grounding/judge/activity meters but no claim-verdict breakdown, no confidence, no "why". | **MEDIUM** |
| 9 | Inference-chain (fact→interpretation→inference→conclusion) not modeled (#7) | Same root cause as #1; addressed by the same fix (see below) rather than a separate 4-stage pipeline, to avoid a second LLM call per turn. | **MEDIUM** (folded into #1) |

Nothing here changes *who* wins any specific historical debate by fiat — all changes are to the *evaluation mechanism*, and are exercised by the new tests in section 6 without hardcoding a winner.

## 4. Correction plan (implemented)

1. **`arena/evidence.py`**
   - Expanded claim verdict enum to `SUPPORTED / PARTIALLY_SUPPORTED / NOT_SUPPORTED / CONTRADICTED / INSUFFICIENT_EVIDENCE`, plus a compact `overclaim` boolean per claim (does the claim add an inference beyond what the evidence entails).
   - Added `engaged` field (`direct / partial / none / na`) — whether the speech directly engaged the opponent's specific claim, evidence, or reasoning (not just a related but different point).
   - `grounding_score` is no longer a bare LLM guess: added `compute_deterministic_grounding()`, a pure function that derives a 0-100 score from the verdicts + overclaim flags, then blended 60/40 (deterministic/LLM) with the model's own estimate — anchoring the number in something auditable.
   - Added `classify_source(url)` / `score_source_credibility(records)`: a rule-based domain-tier classifier (peer-review/gov/edu > research orgs > reputable news > blogs > forums/social), blended 50/50 with the LLM's `citation_credibility` guess whenever real URLs were retrieved this turn.
   - Added a guardrail: if `engaged == "none"` (non-responsive), `rebuttal` is capped at 4/10 server-side regardless of what the LLM scored it, so fluent-but-unresponsive turns can't buy a high rebuttal score.
   - Added explicit judge-fairness and concession-fairness instructions to the prompt.
2. **`arena/research_planner.py`** — added claim-targeted queries built from the opponent's actual last argument (not just the topic), alongside the existing topic-level queries (additive, not a replacement).
3. **`arena/agents.py`**
   - `verify_node` now passes this turn's `evidence_log` records into `run_combined_assessment` for source-credibility blending, and stores `overclaim`/`verdict` per claim in `claims_log`.
   - `score_node` now applies a **contradiction penalty** (-10 composite points, once per newly-detected contradiction) and an **overclaim penalty** (-5 per flagged claim this turn), clamped at 0, and surfaces both in `last_weighted` for transparency.
   - `summary_node` computes a `confidence` label (`HIGH / MODERATE / TOO_CLOSE_TO_CALL`) from the margin relative to total combined score, and the summary prompt now receives a real claims-verdict breakdown instead of asking the model to free-associate "what was proven."
4. **`arena/state.py`** — added `confidence: Optional[str]` to `DebateState` (required or LangGraph drops the field — see the existing comment above `last_assessment`).
5. **`frontend/src/components/DebateStats.jsx`** — added a confidence badge next to the winner banner and a compact claim-verdict ledger (counts of Supported / Partially / Insufficient / Not Supported / Contradicted, per agent) sourced from `state.claims_log`, which was already present in the payload but unused by the UI.

No new debate engine, no second scoring pipeline, no LangGraph node topology changes — every fix modifies an existing node's internals or extends the existing state schema.

## 5. Before / after

**Claim verification** — before: `{"claim": "...", "verdict": "SUPPORTED"}` for *any* claim entailed even loosely by the evidence, including stacked inferences. After: a claim like "AI threatens developers' livelihoods" resting only on a code-quality study now gets `verdict: PARTIALLY_SUPPORTED (or INSUFFICIENT_EVIDENCE)`, `overclaim: true`, and the deterministic grounding component reflects that instead of inheriting the strength of the underlying fact.

**Rebuttal** — before: any fluent paragraph could score 8-10/10 regardless of whether it addressed the opponent's actual point. After: `engaged` is explicitly scored, and a `none` (non-responsive) rebuttal is capped at 4/10 no matter how well-written.

**Contradiction handling** — before: detected and displayed, but worth 0 points either way. After: -10 composite points per newly-detected contradiction.

**Scoring formula** — unchanged in its 35/25/20/10/10 weighting (it was already correct); only the *inputs* (grounding, rebuttal) are now more rigorously derived, plus the two new penalty terms.

**Winner reporting** — before: always "Elena won" / "Marcus won" with a margin. After: same, plus a `confidence` label, so a 2-point margin out of 400 cumulative points now reads `TOO_CLOSE_TO_CALL` instead of implying a decisive win.

## 6. Tests added (`backend/tests/test_audit_fixes.py`)

Pure-function / no-LLM-call tests (matching the existing `test_momentum.py` style):

1. Deterministic grounding: fully supported claim → high score.
2. Deterministic grounding: overclaim flag drags the score down even when the base verdict is SUPPORTED.
3. Deterministic grounding: NOT_SUPPORTED / CONTRADICTED claims → 0.
4. Deterministic grounding: unknown/garbage verdict string treated conservatively (as NOT_SUPPORTED), not crashing.
5. Source credibility: `.gov`/peer-review domain → HIGH tier / high score.
6. Source credibility: LinkedIn/forum → LOW tier / low score; NOT the same as a `.gov` source.
7. Source credibility: empty record list → neutral default, doesn't crash.
8. Confidence banding: near-tied composite scores → `TOO_CLOSE_TO_CALL`.
9. Confidence banding: large margin → `HIGH`.
10. Confidence banding: mid-range margin → `MODERATE`.
11. Research planner: claim-targeted query differs between two different opponent arguments on the same topic (proves it's not just topic-templated).
12. Research planner: Elena and Marcus get equally many, equally-shaped queries for the same inputs (symmetry regression guard).
13. `score_node` contradiction penalty: same base inputs, with vs. without a detected contradiction, produces a strictly lower composite when the contradiction is present.
14. `score_node` overclaim penalty: same, for a flagged-overclaim claims list.
15. `score_node`: no hardcoded winner — verified by asserting the function is a pure transform of `state`, run once with Elena-favorable and once with Marcus-favorable synthetic `last_assessment` inputs, and each wins its own case.

## 7. How to run

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
# or: python main.py   (Rich CLI)

# Tests
cd backend
pytest tests/ -v

# Frontend
cd frontend
npm install
npm run dev
```

## 8. Remaining limitations (not fixed, by design)

- Source credibility tiering is a static domain allowlist — it doesn't verify the underlying page still matches its historical reputation, and unknown domains get a neutral middle score rather than a researched one.
- The deterministic grounding blend (60% rule / 40% LLM) is a documented, reasonable default, not a "solved" calibration — it should be revisited against a labeled evaluation set if the project ever builds one (`scripts/run_evaluation.py` / `scripts/report_agreement.py` already exist and are the natural place to do that).
- `engaged`/`overclaim` are still single-pass LLM judgments (cheaper than a second verification call, per the project's existing 1-call design), so they inherit whatever the judge model gets wrong on a given turn — the deterministic math and penalties bound *how much* that can matter, they don't eliminate LLM error.
- `MODEL_PROVIDER=groq` with a small `MAX_OUTPUT_TOKENS` (default 200) leaves limited headroom for the slightly larger JSON payload; field names were kept short specifically for this reason, but very verbose model completions could still truncate — bump `MAX_OUTPUT_TOKENS` in `.env` if you see JSON parse fallbacks in the logs.
