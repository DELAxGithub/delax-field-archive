# CLAUDE.md

このファイルはClaude Code / Claude Projectが本リポジトリを扱うときの前提知識。

## プロジェクト概要

DELAX Field Archive：マラガ拠点の映像作家デラ（Hiroshi Kodera / 株式会社DELAX代表）の街歩き・自転車撮影素材を資産化し、たっちレディオYouTubeチャンネルでAmbient Walk/Ride Tour動画として連載する統合パイプライン。

## 運用者前提

- NHKドキュメンタリー制作25年
- Vibe Coder（AI駆動の爆速ワークフロー主義、コードは書かず指示する）
- 2026年2月マラガ移住、100日欧州案件獲得ミッション並走中（期限2026/6/20）
- 日本語でのやり取りが基本

## 応答スタイル

- 簡潔・機知に富んだトーン
- 「共に戦場を生き抜くビジネスパートナー」として伴走
- 過度な確認や前置きは不要、推奨を明確に出す
- 100日ミッションと矛盾する提案は避ける（時間対効果最優先）

## シリーズコード

| コード | 意味 |
|---|---|
| DWT | DELAX Walking Tour |
| DBT | DELAX Bike Tour |

命名規則：`{SERIES}_EP{###}_{location-slug}_{YYYYMMDD}`

## episode.yaml スキーマ

`episodes/_template/episode.yaml` 参照。大分類：

- **capture**: 撮影メタ（自動取得）
- **geo**: GPS・場所情報（自動取得）
- **weather**: 気象（自動取得）
- **creative**: タイトル・テーマ等（人間入力）
- **publish**: 公開管理（公開時に追記）

## 自動取得の優先順位

スクリプト実行時に Claude が補完できる項目は可能な限り自動化する。人間（デラ）には creative セクションのみ対話で聞く。

### 自動取得ソース

| 項目 | ソース |
|---|---|
| shot_date, duration, fps 等 | ffprobe |
| GPS / GPX | スマホStrava併走で取得 |
| location_name, landmarks | OpenStreetMap Nominatim（無料） |
| weather | Open-Meteo API（無料・無制限） |

### 人間入力項目

- episode_title
- theme / mood
- chapters[] ラベル
- highlight_moments[]
- music_policy
- notes

## 機材別ワークフロー

### Insta360 X5（DWTシリーズ主役）
1. Insta360 Studioで取り込み
2. **AI Face Blur** 必須（GDPR対応）
3. Reframe編集 → エクスポート

### Sony ZV-E10 II（DBTシリーズ主役）
1. ローカル取り込み
2. DaVinci Resolve **Face Refinement + Blur** 必須
3. 通常編集

## コミット方針

- 動画・音声素材は **絶対にcommitしない**（.gitignore で除外済）
- YAML、GPX、最終サムネPNG、ドキュメントのみ残す
- エピソード単位でブランチ切らず、main 直接commitでOK（小規模運用）

## 禁則

- 素材ファイルをcommitしそうになったら警告する
- エピソードIDの重複を検知したら必ず指摘する
- 過度に汎用化されたフレームワーク提案はしない（YAGNI優先）

## 9:16 ショート レンダリング (2026-04-26 注入)

派生クリップ (`creative.highlight_moments[]`) を 1080×1920 縦動画として書き出す。
仕様: `docs/short-render-spec.md`、雛形: `scripts/render_short.py` (skeleton)。

### マルチプラットフォーム safe zone (要厳守)

YouTube Shorts / Instagram Reels / TikTok 全てに同じ動画を出す前提:
- **クリティカル要素 (場所テロップ等)**: `x=60..916, y=210..1550`
- **装飾要素 (シリーズロゴ等)**: 上部 `y=0..210` も使用可
- 中央寄せ字幕の最大幅: **752px**

これらは TikTok の右側 164px (action button stack) と下部 370px (広告 caption)
を前提とした最厳値。動かす前に必ず spec doc を読むこと。

### 流用元

たっちレディオショート (`~/src/90_サイドワーク/たっちレディオショート/pipeline/`) で
2026-04-26 に 785/784 で動作検証済みの safe zone 値・ヘッダー帯・halo テキスト・
角丸・影 などのデザインプリミティブを持ち込んでいる。
キャラ口パク・カラオケ字幕・話者ピルは**流用しない** (ノーナレ・環境音の矜持)。

## 30-50分 長尺レンダリング (Draft v0 / 2026-04-27 起草、未実装)

DWT/DBT 本編 (5-15分) では 1M views ジャンルに届かない。リサーチ 5 チャンネルから **B-Music 型 (Abao Vision 系)** = ノーカット 30-50分 + 絵で勝つ + Lofi BGM 乗せ + 多言語 SEO を採用。
仕様詳細: [docs/long-form-spec-v0.md](./docs/long-form-spec-v0.md)
リサーチ材料: `~/Dropbox/delax-reports/delax-field-archive/_research/`

### 主要設計判断 (機材リサーチ確定後)
- **撮影**: Single Lens 4K60fps (FlowState) を普段運用、8K 360 reframe は構図後決め回のみ
- **HDR**: HLG / Rec.2020 / 10bit / HEVC で出す (HDR10/Dolby Vision は不要)
- **BGM**: Storyblocks の月一括 DL → ローカル「BGM ライブラリ」フォルダ → ffmpeg `acrossfade` で自動ミックス。Suno は YouTube monetization リスクで使わない
- **書き出し**: 通常は ffmpeg 一発、色補正回のみ DaVinci Resolve Python API (Adobe 不使用方針)
- **サムネ**: 絵で勝つ (Abao 系)、テキスト爆盛りの Maximiniano 系は採用しない

### 実装着手予定
1. ffmpeg HLG ノーカット書き出し
2. 章マーカー + 場所テロップ overlay (render_short.py の機構流用)
3. BGM 自動ミックス (ffmpeg)

1〜3 で MVP、1〜2日。テスト素材: `~/src/_workdir/long-form-pipeline/source/マルセイユ.mp4` (16:08 / 4K HEVC)。

### ファイル配置の3層分離 (2026-04-27 確定)

撮影〜配信のファイルは役割で 3 層に分け、`~/src/` 配下を汚さない:

| 層 | 置き場 | 補足 |
|---|---|---|
| **撮影 raw** (`.MP4` / `.insv` 等) | 外付け SSD のまま参照 | ローカルにコピーしない。ffmpeg は外付けから直読みできる |
| **中間ファイル** (reframe 出力 / プレビュー) | `/tmp/` or `~/src/_workdir/` | 作業中のみ。永続化せず作業後に削除 |
| **最終生成物** (短尺 mp4 / サムネ) | `$DELAX_REPORTS_ROOT/delax-field-archive/<episode-id>/` | DELAX 共通規約。`render_short.py --output` 省略時はここに自動出力 |

`render_short.py` のデフォルト出力先は `$DELAX_REPORTS_ROOT/delax-field-archive/<episode-id>/short_<stem>.mp4`。
エピソードID未確定時は `_unsorted/` 配下。`$DELAX_REPORTS_ROOT` 未設定時は `~/Dropbox/delax-reports/`。
