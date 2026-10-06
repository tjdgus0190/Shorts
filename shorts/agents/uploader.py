"""업로더: YouTube Data API v3로 업로드 (OAuth 리프레시 토큰 사용)."""
from __future__ import annotations

import logging
import os

from .base import Context

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def credentials():
    from google.oauth2.credentials import Credentials

    cid, secret, refresh = (os.environ.get(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))
    if not (cid and secret and refresh):
        return None
    return Credentials(None, refresh_token=refresh, client_id=cid, client_secret=secret,
                       token_uri="https://oauth2.googleapis.com/token", scopes=SCOPES)


def run(ctx: Context, plan: dict, effects: dict) -> dict:
    ucfg = ctx.cfg["upload"]
    if not ucfg.get("enabled", True):
        return {"status": "skipped", "reason": "upload.enabled=false"}
    creds = credentials()
    if creds is None:
        return {"status": "skipped", "reason": "YT_* 시크릿 없음"}

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    title = plan["title"]
    if "#shorts" not in title.lower() and len(title) <= 88:
        title += " #shorts"
    description = plan.get("description", "")
    if plan.get("comment_question"):
        description += f"\n\n💬 {plan['comment_question']}"
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
            "tags": [t for t in plan.get("tags", []) if t][:15],
            "categoryId": ucfg.get("category_id", "24"),
            "defaultLanguage": "ko",
            "defaultAudioLanguage": "ko",
        },
        "status": {
            "privacyStatus": ucfg.get("privacy", "private"),
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": bool(ucfg.get("contains_synthetic_media", True)),
        },
    }
    media = MediaFileUpload(str(ctx.run_dir / effects["final"]), mimetype="video/mp4",
                            chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    log.info("업로드 완료: %s", vid)
    return {"status": "uploaded", "video_id": vid, "url": f"https://youtube.com/shorts/{vid}",
            "privacy": resp.get("status", {}).get("privacyStatus")}
