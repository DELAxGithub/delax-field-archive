# Video Passage Pipeline

Passageの「景色を主役にし、記憶を呼び戻す最小限の情報を重ねる」という
考え方を、DBT/DWT動画へ適用するレビュー・レンダリング工程。

## AIツール非依存

Codex、Claude Code、AntigravityなどのAIは、すべて同じ `review.json` を扱う。
HTMLや会話履歴を原本にしない。

```
動画 + GPS/FIT
  -> review.json
  -> review/index.html
  -> 人間の修正指示
  -> AIがreview.jsonを修正
  -> approve（内容ハッシュを記録）
  -> 縦横レンダリング
  -> YouTube限定公開
```

承認後に文言・時刻・デザイン・GPSデータが変わるとハッシュが不一致になり、
レンダリングとアップロードは停止する。

## 1. 初期化

Action 6では、先に `dji_gps_pipeline.py` でGPSと逆ジオコードSRTを作る。
心拍・ケイデンスを使う場合はWahoo等の `.fit` を指定する。

```bash
scripts/video_passage_pipeline.py init \
  --source /Volumes/Sony_Vlog/DJI/2026-06-10/clip.MP4 \
  --gps-csv work/gps.csv \
  --gpx work/route.gpx \
  --srt work/gps-telop.srt \
  --fit work/activity.fit \
  --episode-id DBT_EP003 \
  --location-label "KANAZAWA · ISHIKAWA" \
  --manifest work/DBT_EP003/review.json
```

FITを指定しなければ、心拍・ケイデンスは表示しない。

## 2. 街情報を作る

AIは各cueの次の項目を編集する。

- `eyebrow`: 英字の補助情報。空でもよい
- `copy_horizontal`: 句読点なし、半角スペース区切り、横1行
- `copy_vertical`: 同じ文言を意味のまとまりで1〜2行
- `review_note`: 根拠や要確認事項

事実確認できない固有情報は書かず、映像とGPSから確認できる範囲に留める。

## 3. HTMLレビュー

```bash
scripts/video_passage_pipeline.py review \
  --manifest work/DBT_EP003/review.json
```

`work/DBT_EP003/review/index.html` で縦横を同時確認する。
修正はHTMLではなく `review.json` へ戻す。

## 4. 承認

```bash
scripts/video_passage_pipeline.py validate --manifest work/DBT_EP003/review.json
scripts/video_passage_pipeline.py approve \
  --manifest work/DBT_EP003/review.json \
  --by delax
```

## 5. 縦横書き出し

```bash
scripts/video_passage_pipeline.py render \
  --manifest work/DBT_EP003/review.json \
  --format both
```

短い動作確認は `--duration 30` を付ける。

## 6. YouTube限定公開

説明欄と必要ならサムネを用意して実行する。

```bash
scripts/video_passage_pipeline.py upload-unlisted \
  --manifest work/DBT_EP003/review.json \
  --description work/DBT_EP003/description.txt \
  --thumbnail work/DBT_EP003/thumbnail.jpg \
  --playlist "DELAX Bike Tour"
```

このコマンドは既存の `upload_youtube.py` を `privacy=unlisted` 固定で呼ぶ。

## 実装範囲

| 工程 | 状態 |
|---|---|
| SDカードからAction 6素材取り込み | `/sd-import-dji`側で実装済み |
| 取り込み済み動画の指定 | 本CLIの `--source` で実装 |
| Action 6 GPS抽出・GPX化 | `dji_gps_pipeline.py`で実装済み |
| 逆ジオコード | `dji_gps_pipeline.py`で実装済み |
| FIT心拍・ケイデンス統合 | 入力契約のみ。デコード・同期は未実装 |
| 街情報のLLM生成 | AI作業。API自動呼び出しはしない |
| HTML縦横レビュー | 本CLIで実装 |
| 承認ゲート | 本CLIで実装 |
| Video Passage縦横レンダ | 本CLIで実装 |
| 説明欄・サムネ・字幕 | 既存スクリプトで実装済み |
| YouTube限定公開 | 本CLIから既存アップローダーへ接続 |
