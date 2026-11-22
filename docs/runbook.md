# SimClass demo runbook

This runbook takes a clean checkout to a repeatable demo on a laptop + Mac mini.

## 0. What you need

- Mac mini (Apple Silicon, 32 GB recommended) on the same network as the laptop
- Processing 4.5+ on the laptop
- Python 3.12+ (the repo uses `server/.venv`)
- Optional: Ollama on the Mac mini for the real local LLM

## 1. Clean checkout

```bash
git clone https://github.com/hyejunl33/simclass.git
cd simclass
```

## 2. Start the server

### Mac mini, full mode

```bash
# once
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5:7b-instruct-q4_K_M   # judge

# every demo
SIMCLASS_MODE=full scripts/start_server.sh
```

`start_server.sh` creates `server/.venv` if needed, selects `ASR_MODE=mlx` and
`TTS_MODE=say` on Apple Silicon, and serves on port 8010.

### Laptop, mock mode

No Mac mini or no Ollama:

```bash
SIMCLASS_MODE=mock scripts/start_server.sh
```

Mock mode keeps the full UI, session flow, sample session, and rule-based judge
working with cached responses.

## 3. Point Processing at the server

Edit `app/processing/SimClass/data/server.txt`:

```text
http://<mac-mini-ip>:8010
```

For a local mock server, use `http://127.0.0.1:8010`.

## 4. Run Processing

```bash
scripts/run_processing.sh build   # compile check
scripts/run_processing.sh run     # open the app
```

Or open `app/processing/SimClass/SimClass.pde` in the Processing IDE and press Run.

If the server is unreachable, the app automatically switches to **offline cache
mode**: it loads `data/cached_lesson.json` and `data/cached_personas.json`, keeps
the timer and phase flow, and answers turns with cached student lines. Feedback
still requires the server.

## 5. Verify the whole loop

From the laptop:

```bash
BASE_URL=http://<mac-mini-ip>:8010 scripts/demo_check.sh          # fast
BASE_URL=http://<mac-mini-ip>:8010 scripts/demo_check.sh --judge  # includes 7B judge
```

Expected: `ALL CHECKS PASSED`.

## 6. Demo flow

1. Click **HWP 수업안 불러오기** and select the lesson plan (or use the built-in
   objects-meaning fixture).
2. Review the three personas; click a card to cycle a misconception.
3. Click **수업 시작**.
4. Hold **음성 입력 (hold)**, speak, and release; or type a question and press Enter.
5. Use **다음 단계** to move through 5/17/12/6 minutes, or let the timer advance.
6. Click **수업 종료**; the replay opens with transcript and KT timeline.
7. Click **피드백**; the rubric scores, evidence, and N/A domains appear.
8. Click **보고서 열기** to open the saved Markdown report.
9. Click **새 세션** to run the same lesson and personas again (practice effect).

## 7. Sample session (no live run)

```bash
curl http://127.0.0.1:8010/api/sample/replay | head
curl http://127.0.0.1:8010/api/sample/report.md
```

Fixtures live in `fixtures/sessions/`. The sample timestamps are normalized to a
40-minute lesson.

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| Processing shows `오프라인 캐시 모드` | Check `server.txt`; `curl http://<ip>:8010/health`; firewall |
| HWP parse fails | Use HWP/HWPX with a lesson-plan table; check server logs |
| ASR fails | `ASR_MODE=mlx` on Apple Silicon; microphone permission |
| No student voice | `TTS_MODE=say`; `say -v Yuna "테스트"`; laptop volume |
| Judge falls back to `heuristic_fallback` | `JUDGE_MODEL` 7B is pulled and Ollama is running; see `reports/` |
| Judge quotes rejected | Use 7B; check `validation.rejected_quotes` in the JSON report |
| `processing-java` missing | `scripts/run_processing.sh` uses `~/opt/Processing` or `PROCESSING_BIN` |

## 9. Known limitations

- Sessions and reports are in memory/files on one server; restarting the server
  loses live sessions (sample fixtures and saved reports remain).
- Real-time 40 minutes is long for a demo; use **다음 단계** to advance.
- Visual teaching behaviors (eye contact, gesture, board writing) are `N/A`;
  there is no camera input.
- The rubric is informed by public 초등임용 2차 수업실연 direction, not an
  official scoring sheet.
- The 3B turn model can repeat the same student; the 7B judge is used for scoring.
- HWP parsing targets a table-based lesson plan; unexpected layouts set
  `needs_review=true` and should be corrected through the review API.
- No cloud, auth, multi-user, or fine-tuning in this demo.
