# Rubric judge and evidence validation

After a session ends, SimClass scores the teacher's lesson demonstration against
the transparent rubric in [`rubric.md`](rubric.md). The judge is prompt-only; no
fine-tuning.

## Two stages

1. **Talk-move coding.** The judge codes every teacher turn (`open_question`,
   `press_reasoning`, `revoice`, `link`, `assess`, `feedback_specific`, ...).
2. **Rubric scoring.** For each domain the judge returns a score 0–3, evidence
   quotes, a short reason, and one actionable improvement.

`POST /api/session/{id}/judge` runs both stages synchronously. Because a 7B
judge can take 45–120 seconds, the UI uses the async job API:

- `POST /api/session/{id}/judge/start` → `{job_id, status}`
- `GET /api/judge/{job_id}` → `running | done | error` + report

The job endpoint is idempotent per session, so a retried start returns the
existing job. Both paths write:

- `reports/{session_id}.json` — full structured report
- `reports/{session_id}.md` — Markdown report
- `GET /api/session/{id}/report.md` — the same Markdown over HTTP

The Processing replay screen has a **피드백** button. It runs the judge, shows
the domain scores and evidence, and saves a local Markdown copy under
`~/SimClassReports/`.

## Evidence rules

- A quote is accepted only if it appears in the transcript. Speaker prefixes
  (`교사:`), bracket ids (`[3]`), and echoed phase names are stripped before
  matching.
- Evidence for structure, questioning, assessment, and conditions must come from
  a **teacher** turn. Interaction may cite a teacher or student turn.
- Invalid quotes are rejected. If a scored domain then has no valid evidence,
  the judge retries (up to one retry); otherwise the domain is scored 0.
- Rejected quotes and retry counts are stored in `validation` so the score is
  auditable.

## Domains

| id | Domain | Source |
|---|---|---|
| `structure` | 수업 구조 | transcript, phase timings |
| `questioning` | 발문·의사소통 | transcript + talk moves |
| `interaction` | 학생 중심 상호작용 | transcript + student turns |
| `assessment` | 평가·피드백 | transcript |
| `conditions` | 상황·조건 대응 | transcript + lesson conditions |
| `delivery` | 전달 태도(음성) | ASR audio duration → speech rate |

`delivery` is scored only when at least one teacher turn came from voice input.
Speech rate is computed as Korean characters per second and marked with the
measured rate. Pauses and fillers are not captured yet and are listed under
`not_assessed`.

Visual behaviors (eye contact, facial expression, gesture, board writing,
classroom movement) are always `N/A` in the demo.

## Models

- turn generation: `OLLAMA_MODEL` (default `qwen2.5:3b-instruct-q4_K_M`)
- judging: `JUDGE_MODEL` (recommended `qwen2.5:7b-instruct-q4_K_M`)

The 3B model often fills evidence quotes with `...`; the 7B model produced valid
quotes in testing. If Ollama is unavailable or the judge output is invalid, the
server falls back to a deterministic rule-based judge and labels the report
`heuristic_fallback`.

## Human validation

The harness supports double-coding 20–30% of judged sessions:

```bash
# deterministic sample (default ratio 0.25)
curl 'http://127.0.0.1:8010/api/validation/sample?ratio=0.25'

# submit an independent human coding
curl -X POST http://127.0.0.1:8010/api/validation/<session_id> \
  -H 'Content-Type: application/json' \
  -d '{"rater":"human-1","scores":{"structure":2,"questioning":2,"interaction":2,"assessment":2,"conditions":2},"notes":""}'

# exact agreement + Cohen's kappa
curl http://127.0.0.1:8010/api/validation/agreement
```

Human codings are saved under `reports/validation/` and are git-ignored.

## Caveats

This is not an official scoring sheet. The rubric is informed by the public
direction of 초등임용 2차 수업실연, but official detailed criteria vary by year
and region. Scores are a rehearsal aid and must be read with their evidence.
