from __future__ import annotations

import subprocess
from functools import lru_cache

from PIL import ImageFont


@lru_cache(maxsize=None)
def font_path(family: str = "Noto Sans CJK KR", style: str = "Bold") -> str | None:
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", f"{family}:style={style}"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return out or None
    except (OSError, subprocess.SubprocessError):
        return None


def load_font(size: int, family: str = "Noto Sans CJK KR", style: str = "Bold"):
    path = font_path(family, style)
    if path:
        try:
            # .ttc의 index 1이 KR인 경우가 많지만 fc-match가 고른 파일 기준으로 KR 인덱스를 찾는다
            for idx in range(10):
                f = ImageFont.truetype(path, size, index=idx)
                if "KR" in " ".join(f.getname()) or not path.endswith(".ttc"):
                    return f
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default(size)
