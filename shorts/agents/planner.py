"""기획자: 마케터 보고서에서 주제 1개를 골라 재미 위주 대본/장면 기획."""
from __future__ import annotations

import json

from .base import Context, prompt


def mock_plan(report: dict) -> dict:
    t = report["topics"][0]
    kw = t["keyword"]
    lines = [
        (f"{kw}, 이거 진짜 알고 계셨어요?", "잠깐만요!"),
        (f"오늘 다들 {kw} 검색하고 난리인데요.", "검색량 폭발"),
        ("사실 여기엔 아무도 말 안 해준 비밀이 있습니다.", "숨은 비밀"),
        ("첫 번째, 생각보다 훨씬 오래된 이야기라는 것.", "첫 번째"),
        ("두 번째, 알고 보면 우리 일상과 엄청 가깝다는 것.", "두 번째"),
        ("여러분은 어떻게 생각하세요? 댓글로 알려주세요.", "당신의 생각은?"),
    ]
    return {
        "chosen_rank": t["rank"], "reason": "[mock] fun_score 최상위",
        "title": f"{kw}, 아무도 몰랐던 사실", "hook": lines[0][0],
        "style": "vibrant 3D cartoon illustration, soft studio lighting, high detail",
        "scenes": [
            {"id": i + 1, "narration": n, "on_screen_text": o,
             "image_prompt": f"a playful scene about {kw}, scene {i + 1}, vertical composition"}
            for i, (n, o) in enumerate(lines)
        ],
        "description": f"{kw}에 대한 의외의 사실!\n#쇼츠 #{kw.replace(' ', '')} #상식",
        "tags": [kw, "쇼츠", "상식"], "comment_question": "여러분은 알고 계셨나요?",
    }


def run(ctx: Context, report: dict, feedback: str | None = None) -> dict:
    topics = [{k: t.get(k) for k in ("rank", "keyword", "topic", "traffic", "why_now", "angle",
                                      "target", "fun_score", "risk", "risk_note")}
              for t in report["topics"]]
    user = f"마케터 보고서:\n{json.dumps({'summary': report.get('summary'), 'topics': topics}, ensure_ascii=False, indent=1)}"
    prev = ctx.state.get("plan")
    if feedback and prev:
        user += (f"\n\n[QA 피드백 — 반영해서 다시 기획하세요]\n{feedback}\n\n"
                 f"[이전 기획]\n{json.dumps(prev, ensure_ascii=False)}")
    plan = ctx.llm.complete_json(prompt("planner"), user, mock=lambda: mock_plan(report))
    plan["scenes"] = [s for s in plan.get("scenes", []) if s.get("narration")][:8]
    if not plan["scenes"]:
        raise ValueError("기획에 장면이 없습니다")
    for i, s in enumerate(plan["scenes"], 1):
        s["id"] = i
    plan["title"] = plan.get("title", "")[:95]
    ctx.state["plan"] = plan
    ctx.save("planner", plan)
    return plan
