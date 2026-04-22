# DELAX Field Archive

マラガ拠点の映像作家デラ（株式会社DELAX代表）が、街歩き・自転車・取材ロケで撮影した素材を資産化し、**たっちレディオYouTubeチャンネル**でのAmbient Walk/Ride Tour動画として連載展開するための統合パイプライン。

## シリーズ体系

| コード | シリーズ名 | カメラ |
|---|---|---|
| **DWT** | DELAX Walking Tour | Insta360 X5 主軸 |
| **DBT** | DELAX Bike Tour | Sony ZV-E10 II 主軸 |

命名規則：`{SERIES}_EP{###}_{location-slug}_{YYYYMMDD}`
例：`DWT_EP001_Pedregalejo-Centro_20260428`

## ディレクトリ構成

```
delax-field-archive/
├── README.md              # このファイル
├── CLAUDE.md              # Claude Code 用プロジェクトコンテキスト
├── .gitignore             # 動画素材は対象外
├── docs/
│   ├── workflow.md        # 標準ワークフロー
│   └── face-blur-guide.md # GDPR対応顔ブラー手順
├── episodes/
│   ├── _template/
│   │   └── episode.yaml   # コピペ用テンプレ
│   ├── DWT_EP001/         # 各エピソード
│   │   ├── episode.yaml
│   │   ├── gpx/
│   │   └── thumbnails/
│   └── ...
├── scripts/               # 自動化スクリプト
└── templates/             # サムネ・タイトルカード雛形
```

## コンテンツ方針

- ナレ無しAmbient Walk/Ride Tour
- 場所テロップのみ（GPSログから自動生成）
- 純環境音ベース、BGMは必要時のみ
- NHK品質 × Vibe Coder爆速ワークフロー

## 公開先

**たっちレディオYouTube**（登録者500 / 週刊DL3,000 / Twitter 1万）

プレイリスト分離運用：
- たっちレディオ本編（ポッドキャスト派生）
- Málaga & Beyond Walking
- Cycling Europe

**短期目標**：AdSense収益化ライン到達（登録1,000＋4,000時間）

## 標準ワークフロー（概要）

1. 撮影 → SDカードローカル取り込み
2. `scripts/extract_metadata.py` 実行 → `episode.yaml` 自動項目埋め
3. Claudeと対話 → 残り項目埋め
4. 顔ブラー処理（カメラ別ルート、`docs/face-blur-guide.md` 参照）
5. 本編編集（場所テロップ自動挿入）
6. 書き出し → 派生クリップ候補自動抽出
7. YouTube公開 → Shorts/Reels派生
8. GitHub commit（記録＆資産化）

詳細は `docs/workflow.md` 参照。

## 運用ルール

- **動画素材はcommitしない**（.gitignore で除外）
- 残すのはYAML / GPX / 最終サムネPNG / ドキュメントのみ
- エピソードIDは連番厳守（欠番OK、重複NG）
