from __future__ import annotations

import argparse
import logging
import sys

from .config import ROOT, load_config
from .llm import LLM, LLMError
from .pipeline import Run, rebuild_index, today


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m shorts", description="자동 쇼츠 파이프라인")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="오늘의 쇼츠 1편 제작(및 업로드)")
    r.add_argument("--date", help="YYYY-MM-DD (기본: 오늘, KST)")
    r.add_argument("--config", help="config.yaml 경로")
    r.add_argument("--mock", action="store_true", help="LLM/TTS/이미지 없이 흐름만 검증")
    r.add_argument("--llm", choices=["claude_cli", "gemini", "mock"], help="LLM provider 강제 지정")
    r.add_argument("--no-upload", action="store_true", help="유튜브 업로드 생략")
    sub.add_parser("index", help="data/index.json 재생성")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.cmd == "index":
        rebuild_index()
        return 0

    cfg = load_config(args.config)
    if args.mock:
        cfg["llm"]["provider"] = "mock"
        cfg["tts"]["provider"] = "mock"
        cfg["images"]["provider"] = "placeholder"
    date = args.date or today(cfg)
    run_dir = ROOT / "runs" / date
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        llm = LLM(cfg, args.llm)
    except LLMError as e:
        logging.error("%s", e)
        return 1
    summary = Run(cfg, date, run_dir, llm).execute(upload=not args.no_upload)
    print(f"\n결과: {summary['status']}  ({run_dir / 'final.mp4'})")
    return 0 if summary["status"] in ("success", "qa_failed") else 1


if __name__ == "__main__":
    sys.exit(main())
