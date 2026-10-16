# AI platform core: agent runtime, tracing, evaluation and the AI Ops dashboard

Date: 2026-10-16. Status: design agreed in chat, awaiting review of this written spec.
Parent: PRD #1 (AI integration). Absorbs #5 (AI logging, limits and prompt-injection tests).

## Why

The portal has a working assistant (#2 language model seam, #3 facts, #4 golden-set evaluation, #7 fact tools in
progress). Turning it into an agentic platform, with an advisory agent, chart explanations, crop health guidance and
a knowledge base, needs three things it does not have:

1. **A reusable agent runtime.** The tool loop lives inside `AssistantService`; tools are a list and dispatch is an
   `if`/`elif` chain without typed arguments. No other agent can reuse it.
2. **Observability.** Model calls, tool calls, tokens and latency exist only as log lines. Nothing is kept, so
   neither live traffic nor evaluation can be monitored.
3. **Evaluation that can be trusted and trended.** Scoring is string checks only; the agent's path is not checked;
   there is no injection set, no judge for faithfulness, no repeats; results exist only as a markdown file; CI does
   not gate on them. The live baseline on 2026-10-15 was 3/44, and part of that is the golden set's fault (cases
   with missing or incomplete `fact_values`).

Success means: every agent is a prompt plus typed tools on one loop; every answer, live or in evaluation, leaves a
trace; every change to a prompt, tool or model can be compared run-against-run on a dashboard before it merges.

## Decisions

| Decision | Choice | Reason |
| --- | --- | --- |
| Build or adopt observability | Own span schema in SQLite, OpenTelemetry GenAI attribute names, optional OTLP export | Local-first (ADR 0001), no extra service, Langfuse/Phoenix can be plugged in later through OTLP |
| Agent runtime | Thin in-house runtime; multi-step workflows are plain Python functions | Only the advisory needs several steps; a graph engine is a framework to maintain |
| Judge model | A second local model, of a different family from the assistant's | Fully offline. Its weakness is answered by calibration against human labels |
| Dashboard | `/ops` route in the existing React app, API under `/api/ops`, admin token from `.env` | Traces hold readers' questions; officer sign-in (#12) can replace the token later |

## Architecture

```
backend/csa_portal/ai/
  model.py          language model seam (moved from language_model.py; that module re-exports for one release)
  tools.py          ToolRegistry
  agent.py          Agent, AgentPolicy, AgentResult
  tracing.py        Tracer, TracedModel, span context, optional OTLP exporter
  store.py          SQLite store and migrations
  agents/
    assistant.py    the portal assistant as an Agent: context builder, prompt, tools, grounding
  evals/
    datasets.py     dataset and case models, loading
    scorers.py      deterministic, trajectory, safety, judge, operational
    runner.py       runs cases with repeats, writes eval_runs and eval_results
    cassettes.py    records and replays full model turns
    calibration.py  Cohen's kappa between judge and human labels
  ops_api.py        /api/ops/* routes
backend/evaluations/
  assistant_golden.json, assistant_adversarial.json, cassettes/, baseline.json
frontend/src/ops/   the AI Ops dashboard
```

### Tool registry

A tool is a Python function with one pydantic argument model, registered with a name and description. The
registry produces the JSON schema the model sees from the argument model, validates the model's arguments before
calling, and turns validation errors and `FactsError` into a tool result `{"error": ...}` for the model to read.
A tool returns `ToolOutput(result: dict, facts: list[Fact])`; facts feed grounding.

### Agent loop

`Agent(name, system_prompt, registry, policy)` with `AgentPolicy(max_rounds=4, final_round_without_tools=True)`.
`Agent.run(messages) -> AgentResult(answer, facts, steps)`, where `steps` lists each tool call with its arguments,
outcome and fact count. It is the loop in `AssistantService._tool_answer` today, unchanged in behaviour, moved out
so the advisory, explain-chart and crop agents use the same one.

### Concurrency

The global non-blocking lock becomes a semaphore sized by `CSA_AI_CONCURRENCY` (default 1, matching today) with a
wait of `CSA_AI_QUEUE_SECONDS` (default 5). When the wait runs out the answer is 429 `assistant-busy`, as now.

### Public API

`POST /api/assistant/chat` keeps its response and adds `trace_id`.

## Tracing

`Tracer` keeps the current trace and span in `contextvars`. `TracedModel` wraps any `LanguageModel` and records
one `llm` span per call; the agent loop records `agent` and `tool` spans; workflows record a `workflow` span.

Span attributes use the OpenTelemetry GenAI names: `gen_ai.operation.name`, `gen_ai.request.model`,
`gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.tool.name`, `gen_ai.tool.call.id`. The LM
Studio adapter reads `usage` from the response so tokens are real, not estimated.

**Privacy.** Question and answer text is stored only when `CSA_TRACE_CONTENT=1`. Otherwise a trace keeps a SHA-256
of the question and metadata. Evaluation traces always keep text, since it comes from the datasets.

**Export.** When `CSA_OTLP_ENDPOINT` is set, finished traces are also sent over OTLP/HTTP. Off by default.

## Store

SQLite at `CSA_AI_DB` (default `backend/ai.db`, git-ignored), WAL mode, one writer queue, a `schema_version` table
and numbered migrations. Live traces older than `CSA_TRACE_RETENTION_DAYS` (default 30) are deleted at startup.

| Table | Columns |
| --- | --- |
| `traces` | id, source (`live` or `eval`), agent, model, started_at, duration_ms, status, error_reason, input_tokens, output_tokens, question_hash, question_text, answer_text, eval_run_id |
| `spans` | id, trace_id, parent_id, kind (`agent`, `llm`, `tool`, `workflow`), name, started_at, duration_ms, status, attributes (JSON) |
| `eval_runs` | id, started_at, finished_at, git_sha, dataset, dataset_version, mode (`recorded` or `live`), model, judge_model, repeats, status (`complete` or `partial`), summary (JSON) |
| `eval_results` | id, run_id, case_id, repeat, trace_id, passed, scores (JSON: scorer → value, passed, reason) |
| `labels` | id, result_id, labeller, faithful, helpful (1–5), note, created_at |

## Evaluation

### Datasets

Versioned JSON in `backend/evaluations/`. A case is today's `GoldenCase` plus `expected_tools`: a list of tool
names, each with a subset of arguments that must match.

- **Golden** (44 cases): a fix pass first. Every grounded case gets complete `fact_values` taken from the facts
  module, and `expected_tools` where the question reaches outside the current view.
- **Adversarial** (new, about 20 cases): injection in the question, in the history and in fact fields (a place
  name carrying instructions); requests to issue an official warning; requests to estimate or invent figures; off-
  topic requests.
- Each later agent brings its own dataset.

### Scorers

Each scorer is a pure function `(case, result) -> Score(value 0..1 | None, passed | None, reason)`.

| Scorer | Checks | Gating |
| --- | --- | --- |
| Deterministic | today's five: grounded numbers, right section, required terms, answer kind, hazard disclaimer | yes |
| Trajectory | tool recall and precision against `expected_tools`, argument match, rounds within budget | yes |
| Safety | injection resisted, guidance disclaimer present, no official-warning wording | yes |
| Judge: faithfulness | every claim supported by the facts the agent actually retrieved (given to the judge) | only when calibrated |
| Judge: helpfulness | 1–5 against a written rubric | only when calibrated |
| Operational | latency, tokens, tool calls | never |

The judge runs through the same seam (`complete(output=JudgeVerdict)`), temperature 0, configured by
`CSA_JUDGE_URL` and `CSA_JUDGE_MODEL`. Its model id is stored on the run.

### Calibration

Results are labelled by hand on the dashboard (faithful yes/no, helpful 1–5). Calibration reports Cohen's kappa
between judge and human for faithfulness and a confusion matrix. With fewer than 20 labels, or kappa below 0.6,
judge scores are shown as uncalibrated and do not gate.

### Runner

`uv run python backend/scripts/evaluate.py --dataset golden --mode live --repeats 3 [--judge] [--record]`.
Per case it reports pass^k (passed every repeat) and a flakiness rate. Every run records the git sha and writes to
the store; the markdown report is still written for pull requests. `npm run eval:live` wraps the live call.

### Cassettes and the CI gate

GitHub CI cannot reach a local model, so CI runs recorded mode only, and that limit is stated in the README.
Recorded mode today replays only final answer text, so tools never run in it. Instead, a live run with `--record`
saves each case's full model turns, tool calls included, to `backend/evaluations/cassettes/`. Recorded mode
replays them through `ScriptedModel`, so the real tools, loop and the gating scorers run in CI. CI fails when the
recorded pass rate falls below `baseline.json`. Judge scores are not part of CI.

## AI Ops dashboard

`/ops` in the existing app, chosen in `main.tsx` by path, no router. On first visit it asks for the token
(`CSA_OPS_TOKEN`), keeps it in `sessionStorage` and sends it as `X-Ops-Token`. ECharts with the portal's light and
dark palettes. Headlines state the finding; no explanatory notes.

| View | Contents |
| --- | --- |
| Overview | KPI tiles with change since the last run (eval pass^k, grounded rate, judge faithfulness with a calibrated badge, live p95 latency over 24 h, error rate, requests per day); pass rate over time per scorer, with run markers and a model filter |
| Eval runs | list; run detail with pass rate per scorer and a case-by-repeat heatmap; compare two runs: regressions, fixes, still failing |
| Case | question, answer, every score with its reason, expected against actual tools, the trace |
| Traces | filterable table (agent, status, model, time); span waterfall with durations and tokens; latency histogram; tool usage; error reasons over time |
| Labelling | queue of unlabelled results, keyboard driven; running kappa |

Empty views show the command that fills them.

| Endpoint | Returns |
| --- | --- |
| `GET /api/ops/metrics?window=24h\|7d\|30d` | KPIs and time series |
| `GET /api/ops/eval-runs`, `GET /api/ops/eval-runs/{id}` | runs; one run with case results |
| `GET /api/ops/eval-runs/compare?a=&b=` | regressions, fixes, still failing |
| `GET /api/ops/traces?agent=&status=&cursor=`, `GET /api/ops/traces/{id}` | trace list; one trace with spans |
| `POST /api/ops/labels`, `GET /api/ops/calibration` | save a label; kappa and confusion matrix |

Without a valid token every `/api/ops` route answers 401. Without `CSA_OPS_TOKEN` set, the routes are not mounted.

## Error handling

- **Tracing never breaks an answer.** A failed store write is logged as a warning, counted, and reported by
  `/api/health` as `tracing: degraded`.
- **Judge failure** gives `Score(None, None, "judge-unavailable")`; the run continues and is marked `partial`.
- **Tool errors** go back to the model as tool results and are recorded as spans with `status=error`.
- **Migrations** run at startup; a database newer than the code refuses to open with a clear message.

## Testing

Test-first, in the repo's existing style.

- Unit: registry schema generation and dispatch; agent loop on `ScriptedModel` (round limit, tool errors, no
  tools in the final round); span nesting across tools and nested agents; migrations on a temporary database;
  each scorer; kappa against worked examples; run comparison; cassette record and replay round-trip.
- API: every `/api/ops` route with and without the token, on a seeded fixture database.
- Frontend: Vitest for series and diff building; Playwright on `/ops` with the seeded database (token prompt,
  overview, run compare, trace waterfall) on the browser-test ports.
- CI: the recorded-cassette evaluation gate.
- Step 1 is a pure refactor: existing assistant tests and the recorded evaluation must give identical results.

## Rollout

One pull request per step into `feat/portal-data`, each its own issue under a new PRD.

0. Finish #7 and run the live evaluation: the number before the platform.
1. `ai/` package, `ToolRegistry`, `Agent`; the assistant on them. No behaviour change.
2. Tracer, store, concurrency setting, `trace_id` in the chat response.
3. Evaluation v2: golden-set fix pass, `expected_tools`, adversarial set, trajectory and safety scorers, repeats,
   results in the store, cassettes, CI gate. Closes #5 together with step 2.
4. Local judge, labels, calibration.
5. `/api/ops` and the token.
6. The `/ops` dashboard.

Afterwards each feature in PRD #1 (#6 streaming, #8 view actions, #9 explain chart, #11/#13/#14 advisories, #21
knowledge base, #10 Urdu) is an agent on this runtime and ships with its own dataset.

## Out of scope

- A graph or state-machine engine for agents.
- Hosted models for answering or judging (ADR 0001 still allows a hosted answering model per deployment later).
- User accounts; the token is replaced by officer sign-in when #12 is decided.
- Live evaluation in GitHub CI.
- Alerting (email or chat) on regressions.
