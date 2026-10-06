"""LLM 호출 래퍼.

- claude_cli: Claude Code CLI(`claude -p`)를 호출. GitHub Actions에서는
  `claude setup-token`으로 만든 CLAUDE_CODE_OAUTH_TOKEN(Pro 구독)으로 인증한다.
- gemini: Gemini API 무료 티어(텍스트/이미지 입력).
- mock: 키 없이 전체 흐름을 검증하기 위한 가짜 응답.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

import requests

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


def extract_json(text: str) -> dict | list:
    """모델 응답에서 JSON 본문만 추출한다(코드펜스·앞뒤 설명 허용)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise LLMError(f"JSON을 찾을 수 없음: {text[:200]}")
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise LLMError(f"JSON 파싱 실패: {e}: {text[:200]}") from e


def resolve_provider(cfg: dict) -> str:
    provider = cfg["llm"].get("provider", "auto")
    if provider != "auto":
        return provider
    has_claude = shutil.which("claude") and (
        os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")
    )
    if has_claude:
        return "claude_cli"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    return "mock"


class LLM:
    def __init__(self, cfg: dict, provider: str | None = None):
        self.cfg = cfg
        self.provider = provider or resolve_provider(cfg)
        log.info("LLM provider: %s", self.provider)

    def complete_json(
        self,
        system: str,
        prompt: str,
        *,
        images: list[Path] | None = None,
        mock: Callable[[], dict | list] | None = None,
    ) -> dict | list:
        if self.provider == "mock":
            if mock is None:
                raise LLMError("mock 응답이 정의되지 않음")
            return mock()

        order = [self.provider]
        # Claude 사용량 한도 등으로 실패하면 Gemini로 한 번 더 시도
        if self.provider == "claude_cli" and os.environ.get("GEMINI_API_KEY"):
            order.append("gemini")

        last: Exception | None = None
        for provider in order:
            for attempt in range(2):
                try:
                    if provider == "claude_cli":
                        text = self._claude(system, prompt, images or [])
                    else:
                        text = self._gemini(system, prompt, images or [])
                    return extract_json(text)
                except Exception as e:  # noqa: BLE001 - 다음 시도로 넘김
                    last = e
                    log.warning("%s 호출 실패(%d): %s", provider, attempt + 1, e)
        raise LLMError(f"모든 LLM 호출 실패: {last}")

    def _claude(self, system: str, prompt: str, images: list[Path]) -> str:
        if images:
            listing = "\n".join(f"- {p.resolve()}" for p in images)
            prompt += f"\n\n[검토할 이미지 파일 — Read 도구로 직접 열어 확인하세요]\n{listing}"
        prompt += "\n\n반드시 JSON 하나만 출력하세요. 다른 설명은 쓰지 마세요."
        cmd = [
            "claude", "-p",
            "--output-format", "json",
            "--model", self.cfg["llm"].get("claude_model", "sonnet"),
            "--append-system-prompt", system,
            # 외부 텍스트(트렌드·뉴스 제목)가 프롬프트에 들어가므로 도구는 Read만 허용
            "--tools", "Read" if images else "",
            "--max-turns", "6" if images else "1",
        ]
        if images:
            cmd += ["--allowedTools", "Read"]
        res = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True,
            timeout=self.cfg["llm"].get("timeout_seconds", 300),
        )
        if res.returncode != 0:
            raise LLMError(f"claude 종료코드 {res.returncode}: {res.stderr[-500:] or res.stdout[-500:]}")
        out = json.loads(res.stdout)
        if out.get("is_error"):
            raise LLMError(f"claude 오류: {out.get('result')}")
        return out["result"]

    def _gemini(self, system: str, prompt: str, images: list[Path]) -> str:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise LLMError("GEMINI_API_KEY 없음")
        model = self.cfg["llm"].get("gemini_model", "gemini-2.5-flash")
        parts: list[dict] = [{"text": prompt}]
        for p in images:
            parts.append({"inline_data": {"mime_type": "image/jpeg",
                                          "data": base64.b64encode(Path(p).read_bytes()).decode()}})
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9},
        }
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": key}, json=body,
            timeout=self.cfg["llm"].get("timeout_seconds", 300),
        )
        if r.status_code != 200:
            raise LLMError(f"gemini HTTP {r.status_code}: {r.text[:300]}")
        cands = r.json().get("candidates") or []
        if not cands:
            raise LLMError(f"gemini 빈 응답: {r.text[:300]}")
        return "".join(p.get("text", "") for p in cands[0]["content"]["parts"])
