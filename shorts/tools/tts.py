"""무료 TTS (Microsoft Edge 온라인 TTS, edge-tts) + 단어 단위 타이밍."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import ssl
from pathlib import Path

from ..config import ssl_cafile
from .video import ffprobe_duration, run_ffmpeg

log = logging.getLogger(__name__)


async def _edge(text: str, voice: str, rate: str, out: Path) -> list[dict]:
    import edge_tts
    import edge_tts.communicate as ec

    cafile = ssl_cafile()
    if cafile:  # 사내 프록시 등 사용자 지정 CA
        ec._SSL_CTX = ssl.create_default_context(cafile=cafile)
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    com = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary", proxy=proxy)
    words = []
    with open(out, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append({"text": chunk["text"], "start": start,
                              "end": start + chunk["duration"] / 1e7})
    return words


def even_words(text: str, duration: float, lead: float = 0.1) -> list[dict]:
    """타이밍 정보가 없을 때 글자 수 비율로 단어 타이밍을 추정."""
    tokens = text.split()
    total = sum(len(t) for t in tokens) or 1
    t, span, words = lead, max(duration - lead * 2, 0.1), []
    for tok in tokens:
        d = span * len(tok) / total
        words.append({"text": tok, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    return words


def synthesize(cfg: dict, text: str, out_base: Path) -> dict:
    """text를 음성으로 합성. {'audio': path, 'duration': s, 'words': [...]} 반환."""
    tcfg = cfg["tts"]
    provider = tcfg.get("provider", "edge")
    if provider == "edge":
        out = out_base.with_suffix(".mp3")
        for attempt in range(3):
            try:
                words = asyncio.run(_edge(text, tcfg["voice"], tcfg.get("rate", "+0%"), out))
                dur = ffprobe_duration(out)
                if not words:
                    words = even_words(text, dur)
                result = {"audio": str(out), "duration": dur, "words": words, "provider": "edge"}
                out_base.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
                return result
            except Exception as e:  # noqa: BLE001
                log.warning("edge-tts 실패(%d): %s", attempt + 1, e)
        log.warning("edge-tts 사용 불가 → 무음 mock으로 대체")

    out = out_base.with_suffix(".wav")
    dur = round(0.4 + len(text.replace(" ", "")) * 0.14, 2)
    run_ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(dur), str(out)])
    return {"audio": str(out), "duration": dur, "words": even_words(text, dur), "provider": "mock"}
