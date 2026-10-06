"""장면 이미지 생성.

- cloudflare: Workers AI FLUX.1 schnell (무료 일일 10,000 뉴런 ≈ 100장, 키 필요)
- pollinations: 키 없이도 동작하지만 익명 사용 시 워터마크·402 제한이 잦음
- placeholder: 네트워크 없이 그라데이션+텍스트 카드 생성 (최종 대체 수단)
auto는 위 순서대로 사용 가능한 것을 시도한다.
"""
from __future__ import annotations

import base64
import hashlib
import os
import logging
import random
import textwrap
import time
import urllib.parse
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter

from .fonts import load_font

log = logging.getLogger(__name__)

PALETTES = [
    ((255, 94, 98), (255, 195, 113)),
    ((67, 206, 162), (24, 90, 157)),
    ((131, 58, 180), (253, 29, 29)),
    ((17, 153, 142), (56, 239, 125)),
    ((252, 70, 107), (63, 94, 251)),
    ((255, 175, 189), (100, 65, 165)),
]


def blur_pad(img: Image.Image, w: int, h: int) -> Image.Image:
    """정사각형 등 가로가 넓은 이미지: 흐린 배경 위에 원본을 가운데 배치(쇼츠 스타일)."""
    img = img.convert("RGB")
    bg = fit_vertical(img, w, h, allow_pad=False).filter(ImageFilter.GaussianBlur(w // 25))
    bg = Image.blend(bg, Image.new("RGB", (w, h), (0, 0, 0)), 0.35)
    fg = img.resize((w, int(img.height * w / img.width)), Image.LANCZOS)
    bg.paste(fg, (0, (h - fg.height) // 2))
    return bg


def fit_vertical(img: Image.Image, w: int, h: int, allow_pad: bool = True) -> Image.Image:
    """세로(9:16)로 맞춘다. 원본이 정사각형에 가까우면 blur_pad, 아니면 가운데 크롭."""
    img = img.convert("RGB")
    if allow_pad and img.width / img.height > 0.75:
        return blur_pad(img, w, h)
    target = w / h
    iw, ih = img.size
    if iw / ih > target:
        nw = int(ih * target)
        img = img.crop(((iw - nw) // 2, 0, (iw - nw) // 2 + nw, ih))
    else:
        nh = int(iw / target)
        img = img.crop((0, (ih - nh) // 2, iw, (ih - nh) // 2 + nh))
    return img.resize((w, h), Image.LANCZOS)


def cloudflare(prompt: str, seed: int | None = None, steps: int = 8, timeout: int = 120) -> Image.Image:
    account, token = os.environ["CF_ACCOUNT_ID"], os.environ["CF_API_TOKEN"]
    body = {"prompt": prompt[:2000], "steps": steps}
    if seed is not None:
        body["seed"] = seed
    r = requests.post(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/black-forest-labs/flux-1-schnell",
        headers={"Authorization": f"Bearer {token}"}, json=body, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"cloudflare HTTP {r.status_code}: {r.text[:300]}")
    return Image.open(BytesIO(base64.b64decode(r.json()["result"]["image"])))


def pollinations(prompt: str, w: int, h: int, model: str = "flux", seed: int | None = None,
                 timeout: int = 120) -> Image.Image:
    seed = seed if seed is not None else random.randint(1, 10**6)
    url = (
        "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt[:1500])
        + f"?width={w}&height={h}&model={model}&seed={seed}&nologo=true&private=true"
    )
    token = os.environ.get("POLLINATIONS_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.get(url, timeout=timeout, headers=headers)
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image/"):
        raise RuntimeError(f"이미지가 아닌 응답: {r.headers.get('content-type')}")
    return Image.open(BytesIO(r.content))


def placeholder(text: str, w: int, h: int, seed: str = "") -> Image.Image:
    rnd = random.Random(hashlib.md5((seed or text).encode()).hexdigest())
    c1, c2 = rnd.choice(PALETTES)
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        draw.line([(0, y), (w, y)], fill=tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3)))
    # 장식용 원
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for _ in range(6):
        r = rnd.randint(w // 8, w // 3)
        x, y = rnd.randint(0, w), rnd.randint(0, h)
        od.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, rnd.randint(20, 50)))
    img = Image.alpha_composite(img.convert("RGBA"), overlay.filter(ImageFilter.GaussianBlur(8))).convert("RGB")
    draw = ImageDraw.Draw(img)
    font = load_font(int(w * 0.085))
    lines = textwrap.wrap(text, width=9)[:5]
    line_h = int(w * 0.11)
    y = h // 2 - line_h * len(lines) // 2
    for line in lines:
        tw = draw.textlength(line, font=font)
        draw.text(((w - tw) / 2, y), line, font=font, fill="white",
                  stroke_width=max(2, w // 180), stroke_fill=(0, 0, 0))
        y += line_h
    return img


def generate_image(cfg: dict, prompt: str, fallback_text: str, out: Path, seed: int | None = None) -> dict:
    """이미지를 생성해 out에 저장하고 사용한 provider를 반환."""
    icfg = cfg["images"]
    w, h = icfg.get("width", 720), icfg.get("height", 1280)
    provider = icfg.get("provider", "auto")
    if provider == "auto":
        chain = (["cloudflare"] if os.environ.get("CF_ACCOUNT_ID") and os.environ.get("CF_API_TOKEN") else [])
        chain.append("pollinations")
    else:
        chain = [provider]
    calls = {
        "cloudflare": lambda: cloudflare(prompt, seed, icfg.get("cloudflare_steps", 8)),
        "pollinations": lambda: pollinations(prompt, w, h, icfg.get("pollinations_model", "flux"), seed),
    }
    img, used = None, "placeholder"
    for name in chain:
        if name not in calls:
            continue
        for attempt in range(3):
            try:
                img, used = calls[name](), name
                break
            except Exception as e:  # noqa: BLE001
                log.warning("%s 실패(%d): %s", name, attempt + 1, str(e)[:200])
                time.sleep(5 * (attempt + 1))
        if img is not None:
            break
    if img is None:
        used = "placeholder"
        img = placeholder(fallback_text, w, h, seed=str(seed))
    fit_vertical(img, w, h).save(out, quality=92)
    return {"provider": used, "path": str(out)}
