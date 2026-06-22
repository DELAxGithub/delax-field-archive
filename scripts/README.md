# scripts/ ディレクトリ

自動化スクリプト置き場。

## 予定しているスクリプト

- `extract_metadata.py` - ffprobe + GPX解析 + Open-Meteo + Nominatim で episode.yaml 自動埋め
- `generate_derivatives.py` - highlight_moments[] から派生クリップ自動切り出し
- `validate_episode.py` - YAML スキーマ検証・ID重複チェック

実装は次フェーズ。

## DJI Action 6 GPS

GPS Bluetooth Remote Controller 付き素材は、軽量な LRF 内の `djmd`
メタデータから抽出できる。

```bash
scripts/dji_gps_pipeline.py extract \
  --source <clip.LRF> --csv gps.csv --gpx route.gpx

scripts/dji_gps_pipeline.py geocode \
  --csv gps.csv --srt gps-telop.srt --cache geocache.json

scripts/dji_gps_pipeline.py render \
  --source <clip.MP4> --srt gps-telop.srt \
  --output gps-preview.mp4 --duration 90
```

`render` は SRT の各 cue を透明 PNG にして時間指定で焼き込むため、
FFmpeg が libass/subtitles filter なしでビルドされていても動作する。

## Video Passage 正式パイプライン

GPS解析後の街情報を、縦横HTMLでレビューしてから同じデータで書き出す。
AIツールには依存せず、`review.json` を共通の原本として扱う。

詳細: [`docs/video-passage-pipeline.md`](../docs/video-passage-pipeline.md)

```bash
scripts/video_passage_pipeline.py init ...
scripts/video_passage_pipeline.py review --manifest <review.json>
scripts/video_passage_pipeline.py approve --manifest <review.json> --by delax
scripts/video_passage_pipeline.py render --manifest <review.json> --format both
scripts/video_passage_pipeline.py upload-unlisted \
  --manifest <review.json> --description <description.txt>
```
