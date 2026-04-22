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
