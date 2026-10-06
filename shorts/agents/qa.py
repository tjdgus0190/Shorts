"""QA: 자동 측정 + 프레임 기반 LLM 평가로 품질·재미·안전성 검증."""
from __future__ import annotations

import json

from ..tools import video
from .base import Context, prompt

WEIGHTS = {"fun": 0.3, "hook": 0.2, "clarity": 0.125, "visual": 0.125, "subtitle": 0.125, "safety": 0.125}


def technical_checks(cfg: dict, path, silent_ok: bool = False) -> dict:
    info = video.probe(path)
    vol = video.mean_volume(path)
    vcfg = cfg["video"]
    problems = []
    if info["duration"] > 60:
        problems.append(f"길이 {info['duration']:.1f}s > 60s (쇼츠 기준 초과)")
    if info["duration"] < 10:
        problems.append(f"길이 {info['duration']:.1f}s 너무 짧음")
    if (info["width"], info["height"]) != (vcfg["width"], vcfg["height"]):
        problems.append(f"해상도 {info['width']}x{info['height']}")
    if not info["has_audio"]:
        problems.append("오디오 없음")
    elif vol is not None and vol < -40 and not silent_ok:
        problems.append(f"음량 너무 작음({vol} dB) — 무음 TTS일 수 있음")
    return {**info, "mean_volume_db": vol, "problems": problems}


def overall(scores: dict) -> int:
    return round(sum(scores.get(k, 0) * w for k, w in WEIGHTS.items()))


def run(ctx: Context, plan: dict, production: dict, effects: dict, attempt: int) -> dict:
    final = ctx.run_dir / effects["final"]
    # --mock 실행(무음 TTS를 의도한 경우)만 음량 검사를 건너뛴다
    tech = technical_checks(ctx.cfg, final, silent_ok=ctx.cfg["tts"].get("provider") == "mock")
    frame_dir = ctx.subdir(f"qa_frames_{attempt}")
    dur = tech["duration"]
    frames = [video.extract_frame(final, t, frame_dir / f"f{i}.jpg")
              for i, t in enumerate([0.6, dur * 0.3, dur * 0.55, dur * 0.85])]

    user = (
        f"[기획서]\n{json.dumps({k: plan.get(k) for k in ('title', 'hook', 'scenes', 'description')}, ensure_ascii=False, indent=1)}\n\n"
        f"[자동 측정]\n{json.dumps(tech, ensure_ascii=False)}\n"
        f"이미지 생성: {production.get('image_providers')} / TTS: {effects.get('tts_provider')}\n"
        f"(placeholder 이미지나 mock TTS는 품질 감점 대상입니다)\n\n"
        f"첨부한 이미지는 영상의 0.6초, 30%, 55%, 85% 지점 프레임입니다."
    )

    def mock():
        s = {"hook": 75, "fun": 72, "clarity": 80, "visual": 70, "subtitle": 85, "safety": 95}
        return {"scores": s, "overall": overall(s), "pass": True, "issues": ["[mock] 실제 평가 아님"],
                "retry_target": None, "feedback": "mock QA"}

    review = ctx.llm.complete_json(prompt("qa"), user, images=frames, mock=mock)
    scores = {k: int(review.get("scores", {}).get(k, 0)) for k in WEIGHTS}
    review["scores"] = scores
    review["overall"] = overall(scores)
    pass_score = ctx.cfg["qa"].get("pass_score", 70)
    passed = review["overall"] >= pass_score and scores["safety"] >= 60 and not tech["problems"]
    if tech["problems"] and not review.get("retry_target"):
        review["retry_target"] = "effector"
    review["pass"] = passed
    review["technical"] = tech
    review["frames"] = [str(f.relative_to(ctx.run_dir)) for f in frames]
    review["attempt"] = attempt
    ctx.save(f"qa_{attempt}", review)
    return review
