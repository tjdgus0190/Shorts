"""이펙터: TTS 내레이션, 단어 단위 자막, 상단 문구, BGM을 입혀 최종 영상 완성."""
from __future__ import annotations

import logging
from pathlib import Path

from ..tools import music, subtitles, tts, video
from .base import Context
from .producer import render_scene_clips

log = logging.getLogger(__name__)

GAP = 0.25  # 장면 사이 숨 고르기(초)


def run(ctx: Context, plan: dict, production: dict, feedback: str | None = None) -> dict:
    cfg = ctx.cfg
    vcfg = cfg["video"]
    if feedback:  # 자막/싱크 지적을 받으면 말 속도를 낮춘다
        cfg = {**cfg, "tts": {**cfg["tts"], "rate": "+0%"}}
    audio_dir = ctx.subdir("audio")

    voices, durations = [], []
    for s in plan["scenes"]:
        res = tts.synthesize(cfg, s["narration"], audio_dir / f"scene_{s['id']:02d}")
        voices.append(res)
        durations.append(round(res["duration"] + GAP, 3))

    # 전체 길이 제한: 넘치면 뒤 장면부터 잘라낸다
    max_len = vcfg.get("max_seconds", 58)
    while sum(durations) > max_len and len(durations) > 3:
        log.warning("길이 초과(%.1fs) → 마지막 장면 제거", sum(durations))
        durations.pop(); voices.pop()
    scenes = production["scenes"][: len(durations)]

    clips = render_scene_clips(ctx, scenes, durations, "final")
    base = video.concat_videos(clips, ctx.run_dir / "video_noaudio.mp4")
    voice = video.concat_audio([(Path(v["audio"]), d) for v, d in zip(voices, durations)],
                               ctx.run_dir / "voice.wav")

    words, tops, t = [], [], 0.0
    for s, v, d in zip(plan["scenes"], voices, durations):
        words += [{**w, "start": w["start"] + t, "end": w["end"] + t, "scene": s["id"]} for w in v["words"]]
        tops.append({"text": s.get("on_screen_text", ""), "start": t, "end": t + d})
        t += d
    ass = ctx.run_dir / "subtitles.ass"
    ass.write_text(subtitles.build_ass(words, tops, vcfg["width"], vcfg["height"],
                                       vcfg.get("font", "Noto Sans CJK KR")), encoding="utf-8")

    bgm = music.pick(cfg, plan.get("bgm_mood"), seed=f"{ctx.date}-{plan.get('title', '')}")
    final = video.compose_final(base, voice, ass, ctx.run_dir / "final.mp4",
                                bgm["path"] if bgm else None, vcfg.get("bgm_volume", 0.18),
                                total=sum(durations))
    thumb = video.extract_frame(final, min(1.0, sum(durations) / 2), ctx.run_dir / "thumbnail.jpg", 360)
    result = {
        "final": str(final.relative_to(ctx.run_dir)),
        "thumbnail": str(thumb.relative_to(ctx.run_dir)),
        "duration": round(sum(durations), 2),
        "scene_durations": durations,
        "tts_provider": voices[0]["provider"],
        "voice": cfg["tts"]["voice"],
        "bgm": bgm["title"] if bgm else None,
        "bgm_mood": plan.get("bgm_mood"),
        "bgm_credit": bgm["credit"] if bgm else "",
        "word_count": len(words),
    }
    ctx.state["effects"] = result
    ctx.save("effector", result)
    return result
