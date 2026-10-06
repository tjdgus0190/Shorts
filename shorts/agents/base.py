from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..config import ROOT
from ..llm import LLM

PROMPTS = ROOT / "shorts" / "prompts"


@dataclass
class Context:
    cfg: dict
    llm: LLM
    run_dir: Path
    date: str
    state: dict = field(default_factory=dict)

    def save(self, name: str, data) -> Path:
        path = self.run_dir / f"{name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def subdir(self, name: str) -> Path:
        d = self.run_dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d


def prompt(name: str, **kwargs) -> str:
    text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    for k, v in kwargs.items():
        text = text.replace("{" + k + "}", str(v))
    return text
