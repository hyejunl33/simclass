from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path

import httpx

DEFAULT_MOCK = "물건의 의미는 무엇일까요?"


def transcribe_bytes(data: bytes) -> tuple[str, str]:
    mode = os.getenv("ASR_MODE", "mock").strip().lower()
    if not data:
        raise ValueError("Empty audio")
    if mode == "mock":
        return DEFAULT_MOCK, "mock"
    if mode == "http":
        url = os.getenv("ASR_URL", "http://127.0.0.1:8001/asr")
        payload = {"filename": "audio.wav", "data_base64": base64.b64encode(data).decode("ascii")}
        with httpx.Client(timeout=60.0) as client:
            res = client.post(url, json=payload)
            res.raise_for_status()
            body = res.json()
        return str(body.get("text", "")).strip(), "http"
    if mode in {"mlx", "mlx_whisper"}:
        import mlx_whisper  # type: ignore

        model = os.getenv("WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fp:
            fp.write(data)
            path = Path(fp.name)
        try:
            result = mlx_whisper.transcribe(str(path), path_or_hf_repo=model, language="ko")
            return str(result.get("text", "")).strip(), "mlx_whisper"
        finally:
            path.unlink(missing_ok=True)
    raise ValueError(f"Unsupported ASR_MODE: {mode}")
