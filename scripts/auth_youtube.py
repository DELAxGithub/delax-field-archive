#!/usr/bin/env -S uv run --quiet --with google-auth-oauthlib --with google-api-python-client python
"""YouTube OAuth 認可だけ走らせる小スクリプト。

upload_youtube.py 内の get_authenticated_service() と同じ処理を、
動画なしで実行するためのもの。初回 setup と token.json refresh 用。

Firefox 等任意のブラウザで承認したい時は --print-auth-url を使う。
デフォルトはシステムのデフォルトブラウザを起動。
"""
from __future__ import annotations
import argparse
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


CONFIG_DIR = Path.home() / ".config" / "delax-field-archive"
CREDENTIALS_PATH = CONFIG_DIR / "credentials.json"
TOKEN_PATH = CONFIG_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--print-auth-url", action="store_true",
                    help="ブラウザを自動起動せず URL を表示")
    args = ap.parse_args()

    if not CREDENTIALS_PATH.exists():
        raise SystemExit(f"credentials.json not found: {CREDENTIALS_PATH}")

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0, open_browser=not args.print_auth_url)
        TOKEN_PATH.write_text(creds.to_json())
        print(f"[auth] token saved → {TOKEN_PATH}")
    else:
        print(f"[auth] token already valid → {TOKEN_PATH}")

    # 認可確認: チャンネル情報を取って表示
    yt = build("youtube", "v3", credentials=creds)
    res = yt.channels().list(part="snippet", mine=True).execute()
    for ch in res.get("items", []):
        print(f"[auth] ✓ authenticated as: {ch['snippet']['title']} ({ch['id']})")


if __name__ == "__main__":
    main()
