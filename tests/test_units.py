import json
from pathlib import Path

import pytest

from shorts.llm import LLMError, extract_json
from shorts.tools.subtitles import build_ass, chunk_words, ts
from shorts.tools.trends import is_sensitive, parse_rss, parse_traffic
from shorts.agents.qa import overall
from shorts.agents.producer import build_prompt

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
<item><title>라면</title><ht:approx_traffic>500+</ht:approx_traffic>
  <ht:news_item><ht:news_item_title>라면 신제품 출시</ht:news_item_title><ht:news_item_source>A</ht:news_item_source><ht:news_item_url>u</ht:news_item_url></ht:news_item></item>
<item><title>배우 X</title><ht:approx_traffic>2,000+</ht:approx_traffic>
  <ht:news_item><ht:news_item_title>배우 X 교통사고</ht:news_item_title><ht:news_item_source>B</ht:news_item_source><ht:news_item_url>u</ht:news_item_url></ht:news_item></item>
</channel></rss>"""


def test_parse_rss_sorted_by_traffic():
    items = parse_rss(RSS)
    assert [i["keyword"] for i in items] == ["배우 X", "라면"]
    assert items[0]["traffic_num"] == 2000
    assert items[1]["news"][0]["title"] == "라면 신제품 출시"


@pytest.mark.parametrize("raw,num", [("500+", 500), ("2,000+", 2000), ("1만+", 10000), ("", 0)])
def test_parse_traffic(raw, num):
    assert parse_traffic(raw) == num


def test_sensitive_filter_checks_news_titles():
    items = parse_rss(RSS)
    assert is_sensitive(items[0], ["사고"]) == "사고"
    assert is_sensitive(items[1], ["사고"]) is None


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('설명\n```json\n{"a": [1, 2]}\n```\n끝') == {"a": [1, 2]}
    assert extract_json('결과는 {"ok": true} 입니다') == {"ok": True}
    with pytest.raises(LLMError):
        extract_json("no json here")


def test_chunks_break_at_scene_boundary():
    words = [{"text": "가", "scene": 1}, {"text": "나", "scene": 1}, {"text": "다", "scene": 2}]
    assert [[w["text"] for w in c] for c in chunk_words(words)] == [["가", "나"], ["다"]]


def test_build_ass_highlights_current_word():
    words = [{"text": "안녕", "start": 0.1, "end": 0.5, "scene": 1},
             {"text": "{세상}", "start": 0.5, "end": 1.0, "scene": 1}]
    ass = build_ass(words, [{"text": "제목", "start": 0, "end": 1}], 1080, 1920, "Noto Sans CJK KR")
    dialogues = [l for l in ass.splitlines() if l.startswith("Dialogue")]
    assert len(dialogues) == 3
    assert "(세상)" in ass and "{세상}" not in ass  # 중괄호는 ASS 태그로 해석되지 않게 치환
    assert ts(61.5) == "0:01:01.50"


def test_overall_weights():
    assert overall({k: 100 for k in ("hook", "fun", "clarity", "visual", "subtitle", "safety")}) == 100
    assert overall({"fun": 100}) == 30


def test_build_prompt_does_not_duplicate_style():
    style = "vibrant 3D cartoon"
    p = build_prompt("a cat, vibrant 3D cartoon", style)
    assert p.count(style) == 1
    assert build_prompt("a dog", style).count(style) == 1
