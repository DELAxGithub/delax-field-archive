---
project: delax-field-archive
last_updated: 2026-04-29
last_commit: 9f88833 2026-04-22
branch: main
auto_generated: true
---

# delax-field-archive 現状スナップショット

## 一言サマリ
30-50分ノーカット街歩き本編 (DWT/DBT) と 9:16 ショート量産パイプライン。
`/field-render` + `/field-publish` + `/field-shorts` の3スキル体制で本編+ショートの
YouTube 公開まで完結。マルセイユで本編1本+Shorts 1本を unlisted で公開済み。
**git 上は 4/22 の初コミット1個だけだが、4/27〜28 で 11 ファイル分の
パイプライン本体が未コミットで積まれている。コミット最優先。**

## 直近の動き（last 7 days）
- 最終コミット: 9f88833 (2026-04-22) 「initialize DELAX Field Archive with DWT_EP001」
- 以降、**未コミット 11 ファイル**:
  - `scripts/`: render_long.py / render_short.py / analyze_bgm.py /
    extract_thumb_candidates.py / generate_description.py /
    generate_shorts_caption.py / generate_subtitles.py / upload_youtube.py /
    auth_youtube.py
  - `docs/`: long-form-spec-v0.md / short-render-spec.md
  - `episodes/TEST_marseille2_2026-04-02/`（テストエピソード）
  - `CLAUDE.md` も未コミット変更あり
- 公開済み: 本編「春のマルセイユ」16min unlisted (https://youtu.be/AGeuA2bx6xw)、
  Shorts 30s Le Panier (https://youtu.be/isHdcKddMfk)

## 直近の devlog
- **2026-04-28**: tachi-tracker のクロスアカウント運用整理。GCP OAuth client は
  delax-field-archive と同居（`tacchiradioYoutube` プロジェクト）
- **2026-04-27**: 長尺パイプ v0.1→v0.4 拡張（BGM カタログ駆動、ffmpeg acrossfade+loudnorm、
  サムネ候補抽出、多言語説明欄、字幕、YouTube Data API v3 アップ）。
  3スキル体制 (`/field-render` `/field-publish` `/field-shorts`) 完成
- **2026-04-22**: `/walktour-process` スキル + GCP OAuth セットアップ完了。
  マルセイユ素材で end-to-end 検証

## 進行中の判断 / 凍結中
- **未コミット 11 ファイル**: 4/27 の長尺＆ショートパイプライン全成果が反映されていない。
  次セッションで commit & push が最優先候補
- **YouTube `defaultAudioLanguage=zxx` 問題**: API 400 で拒否 → `ja` で送って
  Studio で手動変更が現実解として確定（known issue）
- **YT→Twitter/IG/TikTok 自動連携**: X API 有料化 ($200/月) と Meta API 審査ハードルで
  見送り、手動アップ5分が現実解。将来案: Cloudflare Workers + X API で通知ツイートだけ
  自動化する道筋（凍結中）
- **既知制約**: Read tool の 4K PNG 2000px 制限 → pipeline 内で `sips -Z 1600` で
  `*.preview.jpg` を必ず併出する運用

## Open issues / PR
- N/A（gh issue / PR ともに 0）

## 未解決事項（コード内 TODO/FIXME）
- N/A（コード内 TODO/FIXME ヒットなし）

## カスタムノート（手動編集 OK）
（自由にメモを書いてよい。空でもよい）
