# Human validation checklist

Use this after the judge produces reports. Goal: check that rubric scores and
talk moves are reliable enough to defend, and revise the rubric/prompt when they
are not.

## Sample

Judge at least 5 sessions, then sample 20–30%:

```bash
curl 'http://127.0.0.1:8010/api/validation/sample?ratio=0.25'
```

The included sample session can be used for training the raters:

```bash
curl http://127.0.0.1:8010/api/sample/report.md
```

## Two independent raters

1. Rater A and Rater B each read the rubric (`docs/rubric.md`) and the transcript.
2. Code the five scored domains independently: `structure`, `questioning`,
   `interaction`, `assessment`, `conditions`.
3. Use 0–3:
   - 0 not observed
   - 1 emerging
   - 2 adequate
   - 3 strong
4. Mark visual domains and audio features you cannot observe as `N/A`; do not
   guess.
5. Do not discuss scores before both codings are submitted.

## Submit

```bash
curl -X POST http://127.0.0.1:8010/api/validation/<session_id> \
  -H 'Content-Type: application/json' \
  -d '{"rater":"rater-a","scores":{"structure":2,"questioning":2,"interaction":2,"assessment":2,"conditions":2},"notes":""}'
```

Repeat with `rater-b`.

## Agreement

```bash
curl http://127.0.0.1:8010/api/validation/agreement
```

The response reports:

- `pairs`: number of human/machine score pairs
- `exact_agreement`: proportion of identical scores
- `cohen_kappa`: chance-corrected agreement
- per-domain agreement

Interpretation (guideline, not a hard rule):

| kappa | Reading |
|---|---|
| < 0.20 | poor; revise anchors/prompt |
| 0.20–0.40 | fair; inspect disagreements |
| 0.40–0.60 | moderate; usable with caveats |
| 0.60–0.80 | substantial |
| > 0.80 | strong |

## If agreement is low

1. Read the evidence quotes for each disagreement.
2. Decide whether the transcript supports the score.
3. If the rubric anchor is ambiguous, revise `docs/rubric.md`.
4. If the prompt misreads the anchor, revise `server/app/judge.py`.
5. Re-judge the same sessions and re-code; do not silently keep the old score.

## Reporting

Report the number of double-coded sessions, exact agreement, and kappa per
domain. State that the rubric is informed by public 초등임용 2차 수업실연
direction, not an official scoring sheet.
