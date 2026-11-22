# Mac mini M6 32GB setup and laptop connection

Goal: run FastAPI + Ollama + Whisper + TTS on the Mac mini, and the Processing
sketch on the laptop. The demo stays on the local network; no cloud.

## 0. Network assumptions

- Mac mini and laptop on the same Wi-Fi/LAN.
- Laptop finds the Mac mini by IP, e.g. `192.168.0.42`.
- Port `8010` is open for the FastAPI server. Port `8000` is already used by MomentSearch on this Mac mini, so SimClass uses `8010`.

## Fast path

After the prerequisites below:

```bash
cd simclass
SIMCLASS_MODE=full scripts/start_server.sh
```

## 1. On the Mac mini

### Enable SSH and find the IP

1. System Settings → General → Sharing → **Remote Login** ON.
2. In Terminal:

```bash
ipconfig getifaddr en0
whoami
```

Note the IP and username. From the laptop:

```bash
ssh <username>@<mac-mini-ip>
```

### Install runtime

```bash
# Homebrew (if missing)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install ollama python@3.12 git
brew services start ollama
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5:7b-instruct-q4_K_M   # judge only

# Optional: test TTS
say -v Yuna "안녕하세요. 심클래스입니다."
```

### Clone and install the server

```bash
git clone https://github.com/hyejunl33/simclass.git
cd simclass/server
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-mac.txt
```

`requirements-mac.txt` adds `mlx-whisper` on top of the base requirements.
If `mlx-whisper` is not available on the machine, use `whisper.cpp` and set
`ASR_MODE=http` with an external ASR service instead.

### Run the server

```bash
LLM_MODE=ollama \
OLLAMA_MODEL=qwen2.5:3b-instruct-q4_K_M \
JUDGE_MODEL=qwen2.5:7b-instruct-q4_K_M \
ASR_MODE=mlx \
TTS_MODE=say \
TTS_VOICE=Yuna \
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

Test from the Mac mini and from the laptop:

```bash
curl http://127.0.0.1:8010/health
curl http://<mac-mini-ip>:8010/health
```

Expected: `{"ok":true,"mode":"mock","version":"0.3.0"}` (the mode field is the
LLM mode in the health payload; check the server logs for the active adapters).

### Firewall

If the laptop cannot connect, allow incoming connections for Python in
System Settings → Network → Firewall, or temporarily disable the firewall for
the demo network.

## 2. On the laptop

### Point Processing at the Mac mini

Edit:

`app/processing/SimClass/data/server.txt`

```text
http://<mac-mini-ip>:8010
```

Then open `app/processing/SimClass/SimClass.pde` in Processing and run.

### Verify the loop

1. Click **HWP 수업안 불러오기** and pick a `.hwp` lesson plan.
2. Check the lesson summary and student personas.
3. Hold **음성 입력 (hold)** and say a teacher question.
4. Release; the transcript should appear and student responses should render.
5. Student responses should be spoken via the Mac mini TTS.
6. Click a student card to cycle its misconception; the edit is saved.

## 3. Troubleshooting

| Symptom | Check |
|---|---|
| `연결 실패` | `curl http://<ip>:8010/health` from laptop; firewall; same Wi-Fi |
| `HWP 파싱 실패` | File is HWP/HWPX; server logs; `python-hwpx` installed |
| `ASR 실패` | `ASR_MODE=mlx`; `mlx-whisper` installed; microphone permission |
| No student voice | `TTS_MODE=say`; `say -v Yuna` works; TTS endpoint returns audio |
| LLM slow | Use 3B; check `ollama ps`; close other GPU-heavy apps |
| LLM fallback | `LLM_MODE=ollama`; `ollama serve`; model name matches |

## 4. Demo fallback

If the Mac mini is unavailable:

- Keep `server.txt` at `http://127.0.0.1:8010` and run the server locally.
- `LLM_MODE=mock`, `ASR_MODE=mock`, `TTS_MODE=mock`.
- The judge falls back to the deterministic rule-based mode and the report is
  labelled `heuristic` / `heuristic_fallback`.
- The Processing UI still works with cached/mock responses; the feedback and
  model-quality claims are not part of the fallback demo.
