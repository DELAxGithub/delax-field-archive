---
project: delax-field-archive
last_updated: 2026-04-29
last_commit: 350d676 2026-04-29
branch: main
auto_generated: true
---

# delax-field-archive 現状スナップショット

## 一言サマリ
30-50分ノーカット街歩き本編 (DWT/DBT) と 9:16 ショート量産パイプライン。
`/field-render` + `/field-publish` + `/field-shorts` の3スキル体制で本編+ショートの
YouTube 公開まで完結。マルセイユで本編1本+Shorts 1本を unlisted で公開済み。
**2026-04-29 に v0.4 投入 (c6b0baa) → 独立モデレーション → Medium top3 を fix
(98b440d) → pytest 25/25 通過 (350d676) まで一気に完了。Critical 0、Open issue 0。**

## 直近の動き（last 7 days）
- **350d676** (2026-04-29): test — pytest unit tests 4 ファイル / 25 tests 通過
- **98b440d** (2026-04-29): fix — Medium #1 (jp→ja) + Medium #2 (BGM guard) +
  SRT cue 番号の連続化（segments_to_srt が空 cue を skip する際の番号ずれ修正）
- **0cd3f31** (2026-04-29): chore — historian snapshot refresh
- **c6b0baa** (2026-04-29): feat — 長尺/ショート全パイプライン投入 14 files / 2719 ins
- **9f88833** (2026-04-22): 初コミット
- **未コミット変更**: なし（clean）
- **公開済み**: 本編「春のマルセイユ」16min unlisted (https://youtu.be/AGeuA2bx6xw)、
  Shorts 30s Le Panier (https://youtu.be/isHdcKddMfk)

## 直近の devlog
- **2026-04-28**: tachi-tracker クロスアカウント運用整理（GCP OAuth は
  delax-field-archive と同居、project `tacchiradioYoutube`）
- **2026-04-27**: 長尺パイプ v0.1→v0.4 拡張（BGM カタログ駆動、ffmpeg
  acrossfade+loudnorm、サムネ候補抽出、多言語説明欄、字幕、YouTube アップ）
- **2026-04-22**: `/walktour-process` スキル + GCP OAuth セットアップ完了

## 進行中の判断 / 凍結中
- **YouTube `defaultAudioLanguage=zxx` 問題**: API 400 で拒否 → `ja` で送って
  Studio で手動変更が現実解（known issue、コメントに固定済み）
- **YT→Twitter/IG/TikTok 自動連携**: X API 有料化 ($200/月) と Meta API 審査ハードルで
  見送り、手動アップ5分が現実解。将来案: Cloudflare Workers + X API で通知ツイートだけ
  自動化する道筋（凍結中）
- **既知制約**: Read tool の 4K PNG 2000px 制限 → pipeline 内で `sips -Z 1600` で
  `*.preview.jpg` を必ず併出する運用

## Open issues / PR
- なし（#1 #2 #3 は 2026-04-29 に commit 98b440d / 350d676 で **all closed**）

## 未解決事項（コード内 TODO/FIXME）
- N/A（コード内 TODO/FIXME ヒットなし）

## テスト
- `tests/` 配下に pytest 25 tests / 4 ファイル
  - `test_chapters.py` (9): fmt_ts / parse_chapters_metadata / build_chapter_block
  - `test_subtitles.py` (7): srt_timestamp / segments_to_srt
  - `test_bgm.py` (9): select_bgm_tracks / build_bgm_filter_chain
- 実行: `uv run --quiet --with pytest --with pyyaml --with pillow --with mlx-whisper python -m pytest tests/`

## カスタムノート（手動編集 OK）
（自由にメモを書いてよい。空でもよい）
