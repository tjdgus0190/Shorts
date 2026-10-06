"""ASS 자막 생성: 화면 중앙 하단에 2~3단어씩, 현재 읽는 단어는 노란색으로 강조."""
from __future__ import annotations

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},112,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,8,3,2,60,60,560,1
Style: Top,{font},96,&H00FFFFFF,&H00FFFFFF,&H00000000,&HAA000000,1,0,0,0,100,100,0,0,3,18,0,8,70,70,230,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

HIGHLIGHT = r"{\c&H00E5FF&}"  # ASS는 BGR: 노란색 계열
RESET = r"{\c&HFFFFFF&}"


def ts(sec: float) -> str:
    sec = max(sec, 0)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def chunk_words(words: list[dict], max_chars: int = 11, max_words: int = 3) -> list[list[dict]]:
    chunks, cur = [], []
    for w in words:
        length = sum(len(x["text"]) for x in cur) + len(w["text"])
        new_scene = cur and w.get("scene") != cur[-1].get("scene")
        if cur and (new_scene or length > max_chars or len(cur) >= max_words):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(words: list[dict], top_texts: list[dict], w: int, h: int, font: str) -> str:
    """words: 전체 타임라인 기준 단어 목록 / top_texts: [{'text','start','end'}] 화면 상단 문구."""
    lines = [HEADER.format(w=w, h=h, font=font)]
    for t in top_texts:
        if t.get("text"):
            lines.append(f"Dialogue: 1,{ts(t['start'])},{ts(t['end'])},Top,,0,0,0,,{esc(t['text'])}")
    for chunk in chunk_words(words):
        for i, word in enumerate(chunk):
            start = word["start"]
            # 다음 단어 시작까지 유지해 깜빡임 방지
            end = chunk[i + 1]["start"] if i + 1 < len(chunk) else word["end"] + 0.15
            text = " ".join(
                (HIGHLIGHT + esc(x["text"]) + RESET) if j == i else esc(x["text"])
                for j, x in enumerate(chunk)
            )
            lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Caption,,0,0,0,,{text}")
    return "\n".join(lines) + "\n"
