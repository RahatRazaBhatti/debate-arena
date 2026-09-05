# AI Debate Arena

A multi-agent, tool-using, evidence-grounded debate system built on
LangGraph. Two agents with fixed opposing stances — **Elena** (evidence-
first researcher) and **Marcus** (pragmatic systems thinker) — debate a
topic across five structured phases, grounded in live web search, local
documents, and a statistics dataset, with a human moderator who can
redirect either agent or challenge them at any point mid-debate.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in GROQ_API_KEY and TAVILY_API_KEY
python main.py
```

Offline / no-API-key mode (for testing the state machine without network
calls): `MODEL_PROVIDER=offline python main.py`

## CLI

```bash
python main.py              # start a new debate
python main.py --history    # list saved debates
python main.py --replay ID  # step through a finished debate turn by turn
python main.py --resume ID  # continue an unfinished debate
```

## Architecture

A LangGraph state machine (`arena/graph.py`):

```
moderator -> [elena_tools | marcus_tools] -> strategy -> agent
          -> verify (claim check) -> contradiction_check -> score
          -> (loop back to moderator, one turn per invoke) -> summary
```

**Every `app.invoke()` call processes exactly one turn**, then returns
control to the caller. This is what makes the moderator interrupt
mechanism actually work — `main.py` re-invokes the graph once per turn
and can inject a redirect, a structured challenge, or an exit in between
every single turn, not just once the whole debate has already finished.

## Debate phases

Each phase carries its own instruction to the agents (`arena/phases.py`):

| Phase | Turns | Purpose |
|---|---|---|
| Opening | 2 | State your position, no rebuttal yet |
| Evidence | 2 | Present your strongest supporting evidence |
| Rebuttal | 2 | Directly attack your opponent's weakest point |
| Cross-Examination | 2 | Answer the moderator's targeted question |
| Closing | 2 | Final synthesis, no new evidence |

If the moderator doesn't supply a question when Cross-Examination starts,
one is auto-injected so the phase always happens.

## Evidence & tool suite

Five tools (`arena/tools.py`), all actually invoked during a live debate
(not just defined):

- `web_search` (Tavily) — rotates through 4 stance-specific queries per
  agent (`arena/research_planner.py`) so each of a speaker's turns pulls
  genuinely new evidence instead of reusing turn 1's results
- `search_documents` — local `.txt` document retrieval
- `query_dataset` — auto-fires when the topic matches a real metric in
  `data/stats.json`
- `execute_math` — compares a matched dataset stat against a number the
  opponent cited
- `simulate_growth` — projects a matched stat forward as trend evidence

Every source pulled is kept as a structured record (title/url/snippet,
tagged with which agent used it and on which turn) in `evidence_log`,
not just a flattened text blob.

## Claim verification & citation quality (`arena/evidence.py`)

After each turn, a combined LLM call (`run_combined_assessment`) extracts
the turn's factual claims and checks each one against the evidence
actually gathered that turn, tagging each with one of five verdicts:
`SUPPORTED` / `PARTIALLY_SUPPORTED` / `NOT_SUPPORTED` / `CONTRADICTED` /
`INSUFFICIENT_EVIDENCE`, plus an `overclaim` flag for claims that stack
an unsupported inference on top of a narrower supported fact (e.g. "the
study found code quality issues" -> "therefore AI threatens developers'
livelihoods" — the narrower fact can be SUPPORTED while the stretched
conclusion is not). The resulting **Evidence Grounding Score (0-100)** is
a 60/40 blend of a deterministic score computed from those verdicts
(`compute_deterministic_grounding`) and the LLM's own holistic estimate —
not a bare LLM guess.

Citation credibility is similarly blended: a rule-based domain tier
classifier (`classify_source` / `score_source_credibility` — peer-review
and .gov/.edu domains score highest, professional blogs and social/forum
links score lowest) is averaged 50/50 with the LLM's own credibility
rating whenever real URLs were retrieved that turn.

Rebuttal quality also records `engaged` (`direct` / `partial` / `none` /
`na`) — whether the speech actually addressed the opponent's specific
last claim, evidence, or reasoning. A `none` (non-responsive) turn is
capped at 4/10 on rebuttal regardless of how fluently it's written.

## Contradiction detection (`arena/contradiction.py`, `arena/agents.py::contradiction_node`)

Checks whether a speaker's newest claim contradicts something *they
themselves* said earlier in the same debate (not disagreement with the
opponent - that's the whole point of a debate). Flagged contradictions
show up in the dashboard, cost the speaker composite points (see
Scoring below), and can be surfaced to the offending agent via the
moderator's "Expose Contradiction" action.

## Scoring

Two scoring layers, computed every turn:

**Weighted composite (decides the winner)** - `arena/agents.py::score_node`

| Signal | Weight | Source |
|---|---|---|
| Evidence Grounding | 35% | measured by `verify_node` (deterministic/LLM blend) |
| Rebuttal quality | 25% | AI Judge (subjective, LLM-scored, capped if non-responsive) |
| Logical consistency | 20% | AI Judge (subjective, LLM-scored) |
| Direct engagement | 10% | rule-based lexical overlap (`arena/momentum.py`) |
| Clarity | 10% | AI Judge (subjective, LLM-scored) |

After the weighted sum, two penalties are subtracted (floor 0): **-10
points** if a contradiction was newly detected this turn, and **-5
points per claim** flagged as an overclaimed inference this turn. Both
are surfaced in `last_weighted` for transparency.

Tool usage is **not** a direct winning signal - it only earns credit
indirectly, by producing evidence that raises the grounding score.

The final winner comes with a **confidence label**
(`HIGH` / `MODERATE` / `TOO_CLOSE_TO_CALL`), computed from the winning
margin relative to total cumulative points, so a narrow win reads as
narrow instead of always sounding decisive.

**Activity Score (informational only)** - the original rule-based
momentum score (tool use / concrete numbers / engagement / verbosity,
`arena/momentum.py`) is still computed and shown on the dashboard, but no
longer decides the winner on its own.

## Moderator

The moderator gets a menu every turn:

```
[1] Continue  [2] Challenge Elena  [3] Challenge Marcus
[4] Request Evidence  [5] Request Rebuttal  [6] Ask Clarification
[7] Expose Contradiction  [8] End Debate
```

...or free-form text, which is treated as a direct challenge injected as
the next speaker's opponent context.

## Persistence & replay

Every turn is autosaved to `data/debates/<id>.json` (`arena/persistence.py`)
- a crash or Ctrl-C mid-debate doesn't lose the transcript. `--history`
lists saved debates, `--replay` steps through a finished one, `--resume`
continues an unfinished one.

This is local-file persistence, not the production-grade Postgres
checkpointer LangGraph supports - that's the natural next step if this
needs to run as a real service with concurrent debates.

## Evaluation tooling (`scripts/`)

Two harnesses are included for rigor beyond "it works when I tried it":

- `run_evaluation.py` runs real debates across a topic set and writes a
  CSV with the algorithm's decision - with a `human_winner` column left
  **blank**. There's no honest way to report human-agreement percentages
  without actual humans labeling actual debates; fill that column in by
  hand, then run `report_agreement.py` on the result.
- `compare_models.py` runs the same debate across multiple models (each
  in its own subprocess, since the LLM client is cached at import time)
  and records real, directly-measured latency + decisions per model. It
  does not report quality/factuality numbers - that needs your own
  read-through of the transcripts or the human-eval harness above,
  applied per model.

Neither script contains any pre-filled results. The topic list in
`data/eval_topics.json` is just debate prompts, not data.

## Testing

```bash
pytest tests/ -q
```

Runs against `MODEL_PROVIDER=offline` friendly components with no
network required (LLM-dependent logic has deterministic fallback paths
that are unit tested directly). One test
(`test_integration.py::test_offline_debate`) requires live network
access to Groq and may need to be run separately depending on your
environment's network policy.

## Cost control for free-tier Groq

Two calls used to dominate usage: the AI Judge and claim verification
were separate LLM calls, and web search wasn't actually re-running per
turn (see the fixed caching bug below). Current defaults, per full debate:

| Mode | Turns | LLM calls | Tavily calls |
|---|---|---|---|
| Normal (`TURNS_PER_PHASE=1`, default) | 5 | ~16 | 5 |
| `LITE_MODE=true` | 5 | ~11 | 5 |
| `TURNS_PER_PHASE=2` (fuller debate) | 10 | ~31 | 10 |

Levers, all in `.env`:

- **`TURNS_PER_PHASE`** (default `1`) — the single biggest lever, scales
  every other call linearly. `2` restores the original fuller 10-turn debate.
- **`LITE_MODE`** (default `false`) — skips the per-turn claim-verification
  + AI-judge + contradiction-check call entirely (these three used to be
  3 separate LLM calls; they're now already merged into 1 call via
  `arena/evidence.py::run_combined_assessment`, but `LITE_MODE` cuts that
  remaining call too). Scoring falls back to the free, rule-based Activity
  Score. You lose Evidence Grounding / AI Judge / contradiction detection
  for that run.
- **`MAX_OUTPUT_TOKENS`** (default `200`) — output tokens for full
  debate-speech generation (strategy + agent turns). Raise this if
  speeches look cut off mid-sentence.
- **`ASSESSMENT_MAX_TOKENS`** (default `700`) — output tokens for the
  separate, compact claim-verification / AI-judge / contradiction JSON
  call (`run_combined_assessment`). Deliberately **not** shared with
  `MAX_OUTPUT_TOKENS` above: that call's JSON schema (up to 3 claims,
  each with a verdict enum + overclaim flag, plus 6 scored fields) can
  truncate and fail to parse even when speeches themselves are fine,
  and a parse failure used to be silently recorded as a measured "0" -
  producing a debate where the dashboard shows Evidence Grounding: 0.0%
  and AI Judge: 0.0 for the whole debate despite real evidence and
  arguments happening. If you see `[run_combined_assessment] JSON parse
  failed` in the backend logs, raise this.

## Known limitations / honest gaps


- Persistence is local JSON, not a production checkpointer.
- Claim verification and contradiction detection are single LLM calls
  per turn with graceful fallback on parse failure - they are not
  independently validated against a ground-truth fact-checking dataset.
- The evaluation/comparison harnesses are tooling, not results - running
  them and reporting what comes out is a separate step from building
  this project.
