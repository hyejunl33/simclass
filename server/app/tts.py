from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import httpx


def synthesize(text: str, voice: str | None = None) -> tuple[bytes, str]:
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty text")
    mode = os.getenv("TTS_MODE", "mock").strip().lower()
    if mode == "mock":
        return b"", "mock"
    if mode == "http":
        url = os.getenv("TTS_URL", "http://127.0.0.1:8001/tts")
        with httpx.Client(timeout=60.0) as client:
            res = client.post(url, json={"text": text, "voice": voice or "Yuna"})
            res.raise_for_status()
            return res.content, "http"
    if mode != "say":
        raise ValueError(f"Unsupported TTS_MODE: {mode}")

    voice = voice or os.getenv("TTS_VOICE", "Yuna")
    with tempfile.TemporaryDirectory() as td:
        aiff = Path(td) / "out.aiff"
        wav = Path(td) / "out.wav"
        subprocess.run(
            ["say", "-v", voice, "-o", str(aiff), text],
            check=True,
            timeout=20,
        )
        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@22050", str(aiff), str(wav)],
            check=True,
            timeout=20,
        )
        return wav.read_bytes(), "say"
