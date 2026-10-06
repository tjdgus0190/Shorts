"""제작자: 장면별 이미지 생성 + 켄번스 모션 클립 + 러프컷 편집."""
from __future__ import annotations

import json
import logging
import random
from concurrent.futures import ThreadPoolExecutor

from ..tools import images, video
from .base import Context

log = logging.getLogger(__name__)

CHARS_PER_SEC = 7.5  # 한국어 TTS 대략 속도 (러프컷용 추정치)


def render_scene_clips(ctx: Context, scenes: list[dict], durations: list[float], tag: str) -> list:
    vcfg = ctx.cfg["video"]
    clip_dir = ctx.subdir(f"clips_{tag}")

    def one(args):
        scene, dur = args
        out = clip_dir / f"scene_{scene['id']:02d}.mp4"
        return video.render_clip(ctx.run_dir / scene["image"], dur, out, scene["motion"],
                                 vcfg["width"], vcfg["height"], vcfg["fps"])

    with ThreadPoolExecutor(max_workers=3) as ex:
        return list(ex.map(one, zip(scenes, durations)))


REVISE_SYSTEM = """당신은 쇼츠 제작자입니다. QA 피드백을 반영해 장면별 이미지 생성 프롬프트(영어)를 고쳐 씁니다.
FLUX 모델이 정확히 그릴 수 있도록, 한 장면에 핵심 피사체 1~2개만, 구체적인 사물·색·구도로 묘사하세요.
글자·숫자·로고·실존 인물은 넣지 마세요(모델이 글자를 망칩니다).
출력: {"prompts": [{"id": 1, "image_prompt": "..."}]}"""


def revise_prompts(ctx: Context, plan: dict, feedback: str) -> dict[int, str]:
    scenes = [{k: s.get(k) for k in ("id", "narration", "image_prompt")} for s in plan["scenes"]]
    user = f"[QA 피드백]\n{feedback}\n\n[현재 장면]\n{json.dumps(scenes, ensure_ascii=False, indent=1)}"
    out = ctx.llm.complete_json(
        REVISE_SYSTEM, user,
        mock=lambda: {"prompts": [{"id": s["id"], "image_prompt": s["image_prompt"]} for s in scenes]})
    return {int(p["id"]): p["image_prompt"] for p in out.get("prompts", []) if p.get("image_prompt")}


def build_prompt(base: str, style: str) -> str:
    parts = [base.strip().rstrip(",.")]
    if style and style.lower() not in base.lower():
        parts.append(style)
    parts.append("centered subject, no text, no watermark")
    return ", ".join(parts)


def run(ctx: Context, plan: dict, feedback: str | None = None) -> dict:
    ctx.state["producer_round"] = ctx.state.get("producer_round", 0) + 1
    img_dir = ctx.subdir(f"images_{ctx.state['producer_round']}")
    style = plan.get("style", "")
    rnd = random.Random(f"{ctx.date}-{bool(feedback)}")
    revised = revise_prompts(ctx, plan, feedback) if feedback else {}
    for s in plan["scenes"]:
        if s["id"] in revised:
            s["image_prompt"] = revised[s["id"]]
    scenes = []
    providers = []
    for s in plan["scenes"]:
        full_prompt = build_prompt(s["image_prompt"], style)
        out = img_dir / f"scene_{s['id']:02d}.jpg"
        res = images.generate_image(ctx.cfg, full_prompt, s.get("on_screen_text") or s["narration"],
                                    out, seed=rnd.randint(1, 10**6))
        providers.append(res["provider"])
        scenes.append({
            "id": s["id"], "image": str(out.relative_to(ctx.run_dir)), "prompt": full_prompt,
            "provider": res["provider"], "motion": video.MOTIONS[(s["id"] - 1) % len(video.MOTIONS)],
        })

    est = [max(2.0, len(s["narration"].replace(" ", "")) / CHARS_PER_SEC) for s in plan["scenes"]]
    clips = render_scene_clips(ctx, scenes, est, f"rough_{ctx.state['producer_round']}")
    rough = video.concat_videos(clips, ctx.run_dir / "rough_cut.mp4")
    result = {
        "scenes": scenes, "estimated_durations": est,
        "rough_cut": str(rough.relative_to(ctx.run_dir)),
        "image_providers": {p: providers.count(p) for p in set(providers)},
    }
    ctx.state["production"] = result
    ctx.save("producer", result)
    return result
