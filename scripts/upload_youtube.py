#!/usr/bin/env -S uv run --quiet --with google-auth-oauthlib --with google-api-python-client --with pyyaml python
"""YouTube Data API v3 で長尺動画をアップロード + サムネ + 字幕 + プレイリスト。

セキュリティ方針:
  - デフォルト privacy=private (事故防止)
  - 公開時刻指定 (--publish-at) があれば privacy=private + publishAt で予約公開
  - 公開への切替は YouTube Studio UI で人間が確認後に手動

OAuth credentials:
  ~/.config/delax-field-archive/credentials.json  (Google Cloud Console で desktop OAuth client を作成)
  ~/.config/delax-field-archive/token.json        (初回認可後に自動保存)

Quota:
  videos.insert = 1,600 units / 日 10,000 units → 1日6本まで

使い方:
  scripts/upload_youtube.py \\
      --episode-id DWT_EP002 \\
      --video <out>/long_<stem>.mp4 \\
      [--description description_DWT_EP002_jp.txt] \\
      [--title "Marseille Walking Tour"] \\
      [--thumbnail thumbs/candidate_07_badge.jpg] \\
      [--subtitles subtitles/long_<stem>.jp.srt,subtitles/long_<stem>.en.srt] \\
      [--playlist "DELAX Walking Tour"] \\
      [--privacy private|unlisted|public] \\
      [--publish-at 2026-05-01T10:00:00Z]   # ISO8601 UTC
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

import yaml


# ============================================================
# Paths & constants
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_BASE = Path(
    os.environ.get("DELAX_REPORTS_ROOT", str(Path.home() / "Dropbox" / "delax-reports"))
) / "delax-field-archive"

CONFIG_DIR = Path.home() / ".config" / "delax-field-archive"
CREDENTIALS_PATH = CONFIG_DIR / "credentials.json"
TOKEN_PATH = CONFIG_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

DEFAULT_CATEGORY = "19"   # Travel & Events
DEFAULT_LANGUAGE = "ja"
DEFAULT_AUDIO_LANGUAGE = "ja"   # ISO 639-1 のみ受付。zxx (3文字) は API で 400 になる。Studio で後から変更可
DEFAULT_TAGS = ["WalkingTour", "4K", "Ambient", "DELAX"]


def get_authenticated_service(open_browser: bool = True):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    if not CREDENTIALS_PATH.exists():
        sys.exit(
            f"credentials.json not found at {CREDENTIALS_PATH}\n"
            f"Google Cloud Console で OAuth desktop client を作成して、DL した JSON を上記パスに置く"
        )

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            # open_browser=False の場合は URL を表示するだけ → 任意のブラウザにコピペ可
            creds = flow.run_local_server(port=0, open_browser=open_browser)
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
        print(f"[yt] OAuth token saved → {TOKEN_PATH}")

    return build("youtube", "v3", credentials=creds)


def find_playlist_id(yt, name: str) -> str | None:
    req = yt.playlists().list(part="snippet", mine=True, maxResults=50)
    while req is not None:
        res = req.execute()
        for it in res.get("items", []):
            if it["snippet"]["title"].strip() == name.strip():
                return it["id"]
        req = yt.playlists().list_next(req, res)
    return None


def upload_video(yt, video_path: Path, body: dict) -> str:
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/*")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    print(f"[yt] uploading {video_path.name} ({video_path.stat().st_size / 1e9:.2f} GB)...")
    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"[yt]   progress: {pct}%", end="\r")
    print()
    return response["id"]


def set_thumbnail(yt, video_id: str, thumb: Path) -> None:
    from googleapiclient.http import MediaFileUpload
    media = MediaFileUpload(str(thumb), mimetype="image/jpeg")
    yt.thumbnails().set(videoId=video_id, media_body=media).execute()


def upload_caption(yt, video_id: str, srt_path: Path, lang: str) -> None:
    from googleapiclient.http import MediaFileUpload
    media = MediaFileUpload(str(srt_path), mimetype="application/octet-stream")
    yt.captions().insert(
        part="snippet",
        body={"snippet": {
            "videoId": video_id,
            "language": lang,
            "name": f"{lang.upper()} subtitles",
            "isDraft": False,
        }},
        media_body=media,
    ).execute()


def add_to_playlist(yt, video_id: str, playlist_id: str) -> None:
    yt.playlistItems().insert(
        part="snippet",
        body={"snippet": {
            "playlistId": playlist_id,
            "resourceId": {"kind": "youtube#video", "videoId": video_id},
        }},
    ).execute()


def update_episode_yaml(episode_id: str, video_id: str, video_url: str,
                        kind: str = "long") -> None:
    yaml_path = PROJECT_ROOT / "episodes" / episode_id / "episode.yaml"
    if not yaml_path.exists():
        return
    ep = yaml.safe_load(yaml_path.read_text())
    ep.setdefault("publish", {})
    if kind == "shorts":
        ep["publish"].setdefault("shorts", {})
        ep["publish"]["shorts"]["youtube"] = video_url
        ep["publish"]["shorts"]["youtube_video_id"] = video_id
    else:
        ep["publish"]["youtube_url"] = video_url
        ep["publish"]["youtube_video_id"] = video_id
    yaml_path.write_text(yaml.safe_dump(ep, allow_unicode=True, sort_keys=False))
    print(f"[yt] episode.yaml updated → {yaml_path} (kind={kind})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode-id", required=True)
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--description", type=Path, default=None,
                    help="本体 .txt or .md。省略時は description_<episode-id>_jp.txt を探す")
    ap.add_argument("--thumbnail", type=Path, default=None,
                    help="サムネ JPG。省略時は thumbs/candidate_*_badge.jpg の先頭")
    ap.add_argument("--subtitles", default=None,
                    help="カンマ区切りで SRT path。lang は拡張子前 (.jp.srt / .en.srt) から推定")
    ap.add_argument("--playlist", default=None)
    ap.add_argument("--tags", default=None,
                    help="カンマ区切り追加タグ")
    ap.add_argument("--privacy", default="private",
                    choices=["private", "unlisted", "public"])
    ap.add_argument("--publish-at", default=None,
                    help="ISO8601 UTC、例 2026-05-01T10:00:00Z (privacy=private と併用で予約公開)")
    ap.add_argument("--category", default=DEFAULT_CATEGORY)
    ap.add_argument("--print-auth-url", action="store_true",
                    help="認可URLを表示するだけ (Chromeデフォルト等を避けたい時、Firefox 等にコピペ可)")
    ap.add_argument("--kind", choices=["long", "shorts"], default="long",
                    help="動画種別。shorts は episode.yaml の publish.shorts.youtube に保存 (本編URLを上書きしない)")
    args = ap.parse_args()

    if not args.video.exists():
        sys.exit(f"video not found: {args.video}")

    out_dir = args.video.parent

    # description
    desc_path = args.description
    if not desc_path:
        cand = DEFAULT_OUTPUT_BASE / args.episode_id / f"description_{args.episode_id}_jp.txt"
        if cand.exists():
            desc_path = cand
    if not desc_path or not desc_path.exists():
        sys.exit(f"description not found (tried {desc_path}). 先に generate_description.py")
    description = desc_path.read_text()

    # thumbnail
    thumb = args.thumbnail
    if not thumb:
        thumbs = sorted((out_dir / "thumbs").glob("candidate_*_badge.jpg"))
        thumb = thumbs[0] if thumbs else None

    # tags
    tags = list(DEFAULT_TAGS)
    if args.tags:
        tags.extend([t.strip() for t in args.tags.split(",") if t.strip()])

    # body
    body = {
        "snippet": {
            "title": args.title[:100],
            "description": description[:5000],
            "tags": tags,
            "categoryId": args.category,
            "defaultLanguage": DEFAULT_LANGUAGE,
            "defaultAudioLanguage": DEFAULT_AUDIO_LANGUAGE,
        },
        "status": {
            "privacyStatus": args.privacy,
            "selfDeclaredMadeForKids": False,
            "embeddable": True,
        },
    }
    if args.publish_at:
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = args.publish_at

    # auth & upload
    yt = get_authenticated_service(open_browser=not args.print_auth_url)
    video_id = upload_video(yt, args.video, body)
    video_url = f"https://youtu.be/{video_id}"
    print(f"[yt] ✓ uploaded: {video_url}")

    # サムネ
    if thumb and thumb.exists():
        try:
            set_thumbnail(yt, video_id, thumb)
            print(f"[yt] thumbnail set → {thumb.name}")
        except Exception as e:
            print(f"[yt] ⚠ thumbnail failed: {e}")

    # 字幕
    # 内部ファイル命名 (例: foo.jp.srt) と YouTube API が要求する ISO 639-1 を分離する。
    # YouTube は "ja" を要求するが、社内では歴史的に "jp" を使ってきたので変換マップを噛ます。
    YT_LANG_MAP = {"jp": "ja"}
    if args.subtitles:
        for path_s in args.subtitles.split(","):
            path = Path(path_s.strip())
            if not path.exists() or not path.read_text().strip():
                continue
            # 拡張子から言語推定: foo.jp.srt → jp → ja
            stem_parts = path.name.split(".")
            file_lang = stem_parts[-2] if len(stem_parts) >= 3 else "ja"
            api_lang = YT_LANG_MAP.get(file_lang, file_lang)
            try:
                upload_caption(yt, video_id, path, api_lang)
                print(f"[yt] caption uploaded ({api_lang}) → {path.name}")
            except Exception as e:
                print(f"[yt] ⚠ caption {api_lang} failed: {e}")

    # プレイリスト
    if args.playlist:
        pid = find_playlist_id(yt, args.playlist)
        if pid:
            add_to_playlist(yt, video_id, pid)
            print(f"[yt] added to playlist '{args.playlist}'")
        else:
            print(f"[yt] ⚠ playlist not found: '{args.playlist}'")

    # episode.yaml 更新
    update_episode_yaml(args.episode_id, video_id, video_url, kind=args.kind)

    # 結果記録
    result = {
        "video_id": video_id,
        "url": video_url,
        "title": args.title,
        "privacy": args.privacy,
        "publish_at": args.publish_at,
        "playlist": args.playlist,
        "thumbnail": str(thumb) if thumb else None,
    }
    rj = out_dir / f"youtube_upload_{args.episode_id}.json"
    rj.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"[yt] metadata → {rj}")

    # クリップボード
    try:
        import subprocess
        subprocess.run(["pbcopy"], input=video_url.encode(), check=True)
        print(f"[yt] URL → clipboard: {video_url}")
    except Exception:
        pass

    print(f"\n次のステップ: YouTube Studio で確認")
    print(f"  https://studio.youtube.com/video/{video_id}/edit")


if __name__ == "__main__":
    main()
