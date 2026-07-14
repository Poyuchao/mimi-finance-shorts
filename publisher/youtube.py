"""⑧ YouTube 上傳(UPDATE 3,本機版)。

OAuth 2.0(Desktop app)認證 + YouTube Data API v3 videos.insert(resumable)。
先傳 private(私人 → 不需 OAuth 驗證審核)。

核心:
  get_authenticated_service()  → 認證(首次開瀏覽器,之後讀 token.json)
  upload_video(youtube, path, metadata) → resumable 上傳,回 video_id
  build_youtube_metadata(llm_result)     → 組標題/描述/標籤
"""

from __future__ import annotations

import logging
import os
import random
import time

import config

logger = logging.getLogger(__name__)

# 只要「上傳」權限
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# 這些 HTTP 狀態碼可重試(指數退避)
_RETRIABLE_STATUS = {500, 502, 503, 504}


def get_authenticated_service():
    """回傳已授權的 YouTube service。

    • 有 token.json → 讀取;過期且有 refresh_token → 自動續期
    • 無 token.json(首次)→ 開瀏覽器走 OAuth flow → 存 token.json
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    token_path = config.YT_TOKEN_FILE

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("token 過期,用 refresh_token 續期")
            creds.refresh(Request())
        else:
            if not os.path.exists(config.YT_CLIENT_SECRETS):
                raise FileNotFoundError(
                    f"找不到 {config.YT_CLIENT_SECRETS}。請先到 GCP Console 建立 "
                    "OAuth 2.0 用戶端 ID(應用程式類型:桌面應用程式),下載 JSON "
                    f"命名為 {config.YT_CLIENT_SECRETS} 放專案根目錄。"
                )
            logger.info("首次授權:開瀏覽器登入並同意…")
            flow = InstalledAppFlow.from_client_secrets_file(config.YT_CLIENT_SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)  # 本機開瀏覽器

        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        logger.info("已存 token → %s", token_path)

    return build("youtube", "v3", credentials=creds)


def upload_video(youtube, file_path: str, metadata: dict) -> str:
    """resumable 上傳影片,回傳 video_id。"""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"找不到影片檔:{file_path}")

    body = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": metadata.get("tags", []),
            "categoryId": metadata.get("categoryId", "25"),
        },
        "status": {
            "privacyStatus": metadata.get("privacy", "private"),
            "selfDeclaredMadeForKids": False,
            # 註:AI/合成內容標註 videos.insert 目前無穩定欄位 → 上傳後在 YT 後台手動勾
        },
    }

    media = MediaFileUpload(
        file_path, chunksize=4 * 1024 * 1024, resumable=True, mimetype="video/*"
    )
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    retry = 0
    logger.info("開始上傳 %s(隱私:%s)", file_path, body["status"]["privacyStatus"])
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                logger.info("上傳進度 %d%%", int(status.progress() * 100))
        except HttpError as e:
            if e.resp.status in _RETRIABLE_STATUS:
                retry += 1
                if retry > 5:
                    raise
                sleep = min(2 ** retry + random.random(), 60)
                logger.warning("可重試錯誤 %s → %.1fs 後重試(第 %d 次)",
                               e.resp.status, sleep, retry)
                time.sleep(sleep)
            else:
                raise

    video_id = response["id"]
    logger.info("上傳完成 video_id=%s", video_id)
    return video_id


def build_youtube_metadata(llm_result: dict, has_ai_image: bool = False) -> dict:
    """從 LLM 結果組 YouTube metadata(標題 #Shorts、描述+來源+免責、標籤)。

    has_ai_image=True → 描述加「部分畫面為 AI 生成示意圖」(UPDATE 4)。
    """
    items = llm_result.get("items", [])
    video_title = llm_result.get("video_title", "今日財經重點")

    headlines = "\n".join(f"{i}. {it.get('headline', '')}" for i, it in enumerate(items, 1))
    sources = "、".join(
        dict.fromkeys(it.get("source", "") for it in items if it.get("source"))
    )

    ai_note = f"🎨 {config.IMAGE_DISCLAIMER}\n" if has_ai_image else ""
    description = (
        f"今日股市 {len(items)} 大重點:\n"
        f"{headlines}\n\n"
        f"📊 本集來源:{sources}\n"
        f"{ai_note}"
        f"⚠️ {config.YT_DISCLAIMER}\n\n"
        f"#Shorts #財經 #股市 #台股 #米米財經"
    )

    return {
        "title": f"{video_title} {config.YT_TITLE_HASHTAGS}"[:100],   # YT 標題上限 100 字
        "description": description,
        "tags": config.YT_TAGS,
        "categoryId": config.YT_CATEGORY_ID,
        "privacy": config.YT_PRIVACY,
    }
