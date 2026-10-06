"""마케터 → 기획자 → 제작자 → 이펙터 → QA(재작업 루프) → 업로드 오케스트레이션."""
from __future__ import annotations

import json
import logging
import shutil
import time
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

from .agents import effector, marketer, planner, producer, qa, uploader
from .agents.base import Context
from .config import ROOT
from .llm import LLM

log = logging.getLogger(__name__)

DATA_DIR = ROOT / "data"
STAGE_LABELS = {
    "marketer": "마케터", "planner": "기획자", "producer": "제작자",
    "effector": "이펙터", "qa": "QA", "uploader": "업로드",
}


def now_iso(tz: str) -> str:
    return datetime.now(ZoneInfo(tz)).isoformat(timespec="seconds")


class Run:
    def __init__(self, cfg: dict, date: str, run_dir: Path, llm: LLM):
        self.cfg, self.date, self.run_dir = cfg, date, run_dir
        self.tz = cfg["channel"].get("timezone", "Asia/Seoul")
        self.ctx = Context(cfg=cfg, llm=llm, run_dir=run_dir, date=date)
        self.summary: dict = {
            "date": date, "status": "running", "started_at": now_iso(self.tz),
            "llm_provider": llm.provider, "stages": [], "qa": [],
        }

    def stage(self, name: str, fn, *args, note: str = "", **kwargs):
        entry = {"name": name, "label": STAGE_LABELS[name], "status": "running",
                 "started_at": now_iso(self.tz), "note": note}
        self.summary["stages"].append(entry)
        t0 = time.time()
        log.info("▶ %s %s", STAGE_LABELS[name], note)
        try:
            result = fn(self.ctx, *args, **kwargs)
            entry["status"] = "done"
            return result
        except Exception as e:
            entry["status"] = "failed"
            entry["error"] = f"{type(e).__name__}: {e}"[:1000]
            raise
        finally:
            entry["seconds"] = round(time.time() - t0, 1)

    def execute(self, upload: bool = True) -> dict:
        try:
            report = self.stage("marketer", marketer.run)
            self.summary["marketer"] = {
                "summary": report.get("summary"), "topics": report["topics"],
                "trend_count": len(report.get("raw_trends", [])),
                "excluded": report.get("excluded", []),
            }
            plan = self.stage("planner", planner.run, report)
            prod = self.stage("producer", producer.run, plan)
            eff = self.stage("effector", effector.run, plan, prod)

            max_retries = self.cfg["qa"].get("max_retries", 2)
            attempt = 1
            best = None  # 재작업이 오히려 나빠질 수 있으므로 가장 점수가 높은 회차를 보관
            while True:
                review = self.stage("qa", qa.run, plan, prod, eff, attempt, note=f"{attempt}차")
                self.summary["qa"].append({k: review.get(k) for k in
                                           ("attempt", "scores", "overall", "pass", "issues",
                                            "retry_target", "feedback")})
                if best is None or (review["pass"], review["overall"]) > (best[0]["pass"], best[0]["overall"]):
                    shutil.copy(self.run_dir / eff["final"], self.run_dir / "best.mp4")
                    shutil.copy(self.run_dir / eff["thumbnail"], self.run_dir / "best_thumbnail.jpg")
                    best = (review, json.loads(json.dumps(plan)), json.loads(json.dumps(prod)), dict(eff))
                if review["pass"] or attempt > max_retries:
                    break
                target = review.get("retry_target") or "planner"
                fb = review.get("feedback", "")
                note = f"QA {attempt}차 피드백 반영"
                if target == "planner":
                    plan = self.stage("planner", planner.run, report, feedback=fb, note=note)
                if target in ("planner", "producer"):
                    prod = self.stage("producer", producer.run, plan, feedback=fb if target == "producer" else None, note=note)
                eff = self.stage("effector", effector.run, plan, prod,
                                 feedback=fb if target == "effector" else None, note=note)
                attempt += 1

            review, plan, prod, eff = best
            shutil.copy(self.run_dir / "best.mp4", self.run_dir / eff["final"])
            shutil.copy(self.run_dir / "best_thumbnail.jpg", self.run_dir / eff["thumbnail"])
            self.summary["selected_attempt"] = review["attempt"]
            self.summary.update(plan=plan, production={"image_providers": prod["image_providers"]},
                                effects={k: eff[k] for k in ("duration", "tts_provider", "voice", "bgm")})
            self.export_media(plan, prod, eff)

            if not review["pass"]:
                self.summary["status"] = "qa_failed"
                self.summary["upload"] = {"status": "skipped", "reason": "QA 불합격"}
            elif not upload:
                self.summary["status"] = "success"
                self.summary["upload"] = {"status": "skipped", "reason": "--no-upload"}
            else:
                res = self.stage("uploader", uploader.run, plan, eff)
                self.summary["upload"] = res
                self.summary["status"] = "success"
        except Exception as e:  # noqa: BLE001
            log.error("파이프라인 실패: %s", e)
            self.summary["status"] = "failed"
            self.summary["error"] = f"{type(e).__name__}: {e}"[:1000]
            self.summary["traceback"] = traceback.format_exc()[-3000:]
        finally:
            self.summary["finished_at"] = now_iso(self.tz)
            self.write_summary()
        return self.summary

    def export_media(self, plan: dict, prod: dict, eff: dict) -> None:
        """대시보드용 작은 이미지(썸네일·스토리보드)를 data/에 복사."""
        media = DATA_DIR / "runs" / self.date
        if media.exists():
            shutil.rmtree(media)
        media.mkdir(parents=True)
        shutil.copy(self.run_dir / eff["thumbnail"], media / "thumbnail.jpg")
        board = []
        for s, p in zip(plan["scenes"], prod["scenes"]):
            img = Image.open(self.run_dir / p["image"])
            img.thumbnail((240, 427))
            name = f"scene_{s['id']:02d}.jpg"
            img.save(media / name, quality=80)
            board.append({"id": s["id"], "narration": s["narration"],
                          "on_screen_text": s.get("on_screen_text", ""),
                          "image": f"runs/{self.date}/{name}", "provider": p["provider"]})
        self.summary["storyboard"] = board
        self.summary["thumbnail"] = f"runs/{self.date}/thumbnail.jpg"
        self.summary["video_file"] = f"videos/{self.date}.mp4"

    def write_summary(self) -> None:
        (DATA_DIR / "runs").mkdir(parents=True, exist_ok=True)
        path = DATA_DIR / "runs" / f"{self.date}.json"
        path.write_text(json.dumps(self.summary, ensure_ascii=False, indent=2), encoding="utf-8")
        rebuild_index()


def rebuild_index() -> list[dict]:
    rows = []
    for p in sorted((DATA_DIR / "runs").glob("*.json"), reverse=True):
        s = json.loads(p.read_text(encoding="utf-8"))
        last_qa = (s.get("qa") or [{}])[-1]
        rows.append({
            "date": s["date"], "status": s.get("status"),
            "title": (s.get("plan") or {}).get("title"),
            "overall": last_qa.get("overall"), "qa_attempts": len(s.get("qa") or []),
            "thumbnail": s.get("thumbnail"),
            "youtube_url": (s.get("upload") or {}).get("url"),
            "upload_status": (s.get("upload") or {}).get("status"),
            "duration": (s.get("effects") or {}).get("duration"),
        })
    (DATA_DIR / "index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def today(cfg: dict) -> str:
    return datetime.now(ZoneInfo(cfg["channel"].get("timezone", "Asia/Seoul"))).strftime("%Y-%m-%d")
