# 標準ワークフロー

撮影から公開・アーカイブまでの標準手順。

## 0. 撮影前

- スマホStravaアクティビティ開始（GPX取得用、Walk/Rideどちらも）
- 機材バッテリー・SDカード確認
- 天気・日の出/日の入り時刻チェック（朝ゴールデンアワー活用）

## 1. 素材取り込み

ローカル作業用ディレクトリ（リポジトリ外、例：`~/delax-field-raw/DWT_EP001/`）を作り、以下を配置：

```
DWT_EP001/
├── raw/           # カメラ素材（.insv / .mp4）
├── gpx/           # Stravaエクスポート
└── audio/         # 別録音声（あれば）
```

**このディレクトリはリポジトリに入れない**。リポジトリに残すのは後述のメタのみ。

## 2. メタデータ自動抽出

```bash
python scripts/extract_metadata.py \
  --episode-id DWT_EP001 \
  --raw-dir ~/delax-field-raw/DWT_EP001 \
  --gpx ~/delax-field-raw/DWT_EP001/gpx/strava.gpx
```

実行結果：`episodes/DWT_EP001/episode.yaml` の `capture` / `geo` / `weather` セクションが自動で埋まる。

## 3. クリエイティブ項目の対話入力

Claude Code または Claude Project に以下を依頼：

> `episodes/DWT_EP001/episode.yaml` の creative セクションを埋めたい。順に質問して。

対話で以下を固める：
- episode_title / title_en
- theme / mood / music_policy
- chapters[]
- highlight_moments[]
- notes

## 4. 顔ブラー処理

**GDPR対応必須**。カメラ別ルート（`docs/face-blur-guide.md` 詳細）：

- **Insta360 X5** → Insta360 Studio の AI Face Blur → Reframe書き出し
- **Sony ZV-E10 II** → DaVinci Resolve の Face Refinement + Blur

取りこぼしチェックをプレビューで1回通すこと。

## 5. 本編編集

### 場所テロップの自動挿入

GPXタイムスタンプと `geo.landmarks[]` の `timestamp_sec` を使って、場所名テロップを自動配置。

現状はResolveのSubtitle機能 or Premiereのキャプション機能に手動インポート（自動化は後回し）。

### 編集方針

- カット最小、流れ重視
- 環境音を最優先で残す
- BGMは `music_policy: ambient-only` なら無し、それ以外は控えめに

## 6. 書き出しと派生クリップ

### 書き出し設定

| 媒体 | 解像度 | アス比 | 尺 |
|---|---|---|---|
| YouTube本編 | 4K (3840x2160) | 16:9 | 15-20分 |
| YouTube Shorts | 1080x1920 | 9:16 | 60秒 |
| Instagram Reels | 1080x1920 | 9:16 | 90秒 |
| Twitter | 1920x1080 | 16:9 or 1:1 | 2分20秒以内 |
| LinkedIn | 1920x1080 | 16:9 | 3分以内（案件フック時のみ） |

### 派生クリップ選定

`creative.highlight_moments[]` を元に、本編から該当箇所を切り出し。将来的には `scripts/generate_derivatives.py` で半自動化予定。

## 7. YouTube公開

1. たっちレディオチャンネルにアップロード
2. 適切なプレイリストに追加（Málaga & Beyond Walking / Cycling Europe）
3. チャプター設定（`creative.chapters[]` からコピペ）
4. サムネ設定（`episodes/{ID}/thumbnails/` から選択）
5. `episode.yaml` の `publish` セクション更新

## 8. GitHub commit

```bash
cd delax-field-archive
git add episodes/DWT_EP001/
git commit -m "feat(DWT_EP001): publish Pedregalejo → Centro Histórico"
git push
```

**注意**：素材ファイル（.mp4等）が紛れ込んでないか `git status` で確認。

## 9. 振り返り

次回改善点を `episode.yaml` の `notes` に追記。Vibe Coder的にここが最重要、連載の品質が上がる。

---

## 緊急時ショートカット

「とりあえず1本公開したい、メタは後で」な時：

1. 撮影 → 顔ブラー → 編集 → 公開
2. 公開後に `episode.yaml` の creative / publish をまとめて埋める
3. 連続でやらない（習慣化したらメタが腐る）
