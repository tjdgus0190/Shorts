"""분위기(무드)에 맞는 배경음악 선택·다운로드(캐시)."""
from __future__ import annotations

import logging
import random
import urllib.parse
from pathlib import Path

import requests
import yaml

from ..config import ROOT

log = logging.getLogger(__name__)

LIBRARY = ROOT / "assets" / "bgm" / "library.yaml"
CACHE = ROOT / "assets" / "bgm" / "cache"
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg"}


def load_library(path: Path = LIBRARY) -> dict:
    if not path.exists():
        return {"source": {}, "tracks": []}
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def moods(lib: dict | None = None) -> list[str]:
    lib = lib or load_library()
    return sorted({m for t in lib["tracks"] for m in t["moods"]})


def candidates(lib: dict, mood: str | None) -> list[dict]:
    """1순위 무드가 정확히 일치하는 곡 → 보조 무드 일치 → 전체."""
    primary = [t for t in lib["tracks"] if t["moods"][:1] == [mood]]
    secondary = [t for t in lib["tracks"] if mood in t["moods"] and t not in primary]
    return primary + secondary or lib["tracks"]


def download(lib: dict, track: dict, timeout: int = 60) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / f"{track['title']}.mp3"
    if out.exists() and out.stat().st_size > 10_000:
        return out
    url = lib["source"]["base_url"] + urllib.parse.quote(track["title"]) + ".mp3"
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    if len(r.content) < 10_000:
        raise RuntimeError(f"음원이 너무 작음({len(r.content)} bytes)")
    out.write_bytes(r.content)
    return out


def pick(cfg: dict, mood: str | None, seed: str) -> dict | None:
    """{'path','title','mood','credit'} 또는 None(배경음악 없음)."""
    lib = load_library()
    rnd = random.Random(seed)
    pool = candidates(lib, mood) if lib["tracks"] else []
    # 같은 무드 안에서 앞쪽(1순위 일치) 곡을 우선하되 매일 다른 곡이 나오도록 섞는다
    primary = [t for t in pool if t["moods"][:1] == [mood]]
    order = rnd.sample(primary, len(primary)) + rnd.sample([t for t in pool if t not in primary],
                                                         len(pool) - len(primary))
    for track in order[:4]:
        try:
            path = download(lib, track)
            credit = lib["source"].get("credit", "").format(title=track["title"])
            return {"path": path, "title": track["title"], "mood": mood, "credit": credit}
        except Exception as e:  # noqa: BLE001
            log.warning("배경음악 다운로드 실패(%s): %s", track["title"], e)

    # 라이브러리를 못 쓰면 사용자가 직접 넣어둔 파일(저작권 확인된 음원)을 사용
    bgm_dir = ROOT / cfg["video"].get("bgm_dir", "assets/bgm")
    local = sorted(p for p in bgm_dir.glob("*") if p.suffix.lower() in AUDIO_EXT)
    if local:
        p = rnd.choice(local)
        return {"path": p, "title": p.stem, "mood": mood, "credit": ""}
    return None
