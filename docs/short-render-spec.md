# 9:16 Short Renderer Spec

DWT/DBT 本編から `creative.highlight_moments[]` を派生させる際の **9:16 縦動画レンダラ仕様**。
2026-04-26 にたっちレディオショート (`~/src/90_サイドワーク/たっちレディオショート/pipeline/`) で
詰めた知見を、ノーナレ街歩きショート向けに翻訳した版。

## 出力スペック

- 解像度: **1080×1920** (9:16)
- フレームレート: **30fps**
- 尺: 60秒（YouTube Shorts）/ 90秒（Reels）/ 140秒以内（Twitter）
- コンテナ: H.264/AAC mp4
- ピクセルフォーマット: yuv420p

## マルチプラットフォーム セーフゾーン

YouTube Shorts / Instagram Reels / TikTok の **3プラ全部に出す前提**で
クロスプラットフォーム最厳値を採用（出典: kreatli, postplanify, trymypost 2026 各社調査）。

| プラットフォーム | 上 | 下 | 右 | 左 |
|---|---|---|---|---|
| YouTube Shorts | 180 (auto-hide) | 350 | 120 | 40 |
| Instagram Reels | ~210 | ~310 | ~84-90 | 40 |
| **TikTok 有機** | ~140 | ~324 | **~164** ⚠️最厳 | ~60 |
| TikTok 広告 | ~140 | ~370 | ~164 | ~60 |

→ **クリティカル要素 (場所テロップ・チャプター・進捗バー等) の universal safe zone:**
  **`x = 60..916`（横 856px）, `y = 210..1550`（縦 1340px）**

→ **装飾要素 (シリーズロゴ・ヘッダー帯・章タイトル) は上部 0..210px に配置可**
  （IG/TikTok の username overlay と被ってもブランド識別性は損なわれない設計にする）

→ **中央寄せ字幕の最大幅**: `2 * min(540-60, 916-540) = 752px`
  （中心が x=540 のため右の制約 916 のほうが厳しい → 右に合わせて対称幅で計算）

## レイアウト テンプレ A: 動画フル + 場所テロップ

最も素直な街歩きショート構成。動画素材を画面いっぱいに敷き、場所テロップだけ重ねる。

```
┌─ y=0 ────────────────────────────────┐
│ ▓▓ シリーズロゴ帯 (高さ 130) ▓▓▓▓▓▓▓│ 黒帯 + "DELAX Walking Tour" + #EP001 chip
├─ y=130 ──────────────────────────────┤
│                                      │
│   動画素材 (フル / 1080x1920)         │ Insta360 reframe済み or 16:9素材を
│                                      │   center crop して 9:16 に
│   [場所テロップ y=1300〜1450 oseo)]   │ NHKふれあい街歩き文法
│                                      │
├─ y=1550 ─────────────────────────────┤
│  下部 350px: 何も置かない (YouTube UI) │
└─ y=1920 ─────────────────────────────┘
```

## レイアウト テンプレ B: ヒーロー型 + 動画下半分

エピソードカバー画像 (静止画) を上半分、動画クリップを下半分に配置。
たっちレディオショートに近い構成だが、キャラ口パクは無し。

```
┌─ y=0 ────────────────────────────────┐
│ ▓▓ シリーズロゴ帯 (高さ 130) ▓▓▓▓▓▓▓│ 黒帯
├─ y=130 ──────────────────────────────┤
│   タイトル strip (180px)              │ episode_title 2行
├─ y=310 ──────────────────────────────┤
│   ┌──────────────────────────────┐  │
│   │  サムネ静止画 660x660 (角丸)  │  │ チャプター扉的に使う場合のみ
│   └──────────────────────────────┘  │
├─ y=970 ──────────────────────────────┤
│   動画クリップ 1080x540 (16:9 reframe) │ 場所テロップを overlay
├─ y=1510 ─────────────────────────────┤
│  バッファ + safe zone 下端            │
└─ y=1920 ─────────────────────────────┘
```

## 場所テロップ (NHKふれあい街歩き 文法)

- 位置: 動画の下三分の一に重ねる (y=1300〜1450 内、safe zone 内)
- 構成: **大きな地名 + 小さな英語サブ + 撮影日 (任意)**
  ```
  ペドレガレホ
  Pedregalejo · Málaga · 2026.03.07
  ```
- フォント: ヒラギノ角ゴ W7 (大) + W3 (英語サブ)
- 背景: 半透明黒帯 (rgba(0,0,0,0.55)) または無地（動画コントラスト次第）
- フェード: 800ms in / 1200ms hold / 600ms out
- 出すタイミング: `landmarks[].timestamp_sec` 通過時に 4-6秒表示

実装は `episode.yaml` の `geo.landmarks[]` を読んで自動配置。

## 流用元 (たっちレディオショート 2026-04-26)

`~/src/90_サイドワーク/たっちレディオショート/pipeline/scripts/lipsync_3char.py` から以下を持ち込む候補:

| 機能 | 流用度 | メモ |
|---|---|---|
| safe zone 定数 (`SAFE_*`) | ★★★ そのまま | 上記表と同じ値 |
| `make_stripe_bg()` | × | 黄色ストライプはステッカーブランド固有、街歩きには不要 |
| `round_corners()` | ★★ | サムネ角丸処理に流用 |
| `with_drop_shadow()` | ★★ | サムネに影を付ける時用 |
| `make_static_background()` | ★ 構造のみ | ヘッダー帯の組み方は参考になる |
| `draw_text_with_halo()` | ★★★ | 場所テロップの可読性確保に必須 |
| `find_episode_icon()` | × | サムネは episode.yaml.publish.thumbnail_file から |
| `dim_alpha()` | × | キャラ非アクティブ表現用、不要 |
| `draw_karaoke()` | × | ナレ無しなのでカラオケ字幕は不要 |
| Pillow + ffmpeg レンダ構造 | ★★★ | per-frame PNG → ffmpeg encode の組み立てパターン |

## scripts/render_short.py の役割 (skeleton 段階)

入力:
- `--episode DWT_EP001` （episode.yaml から creative.highlight_moments[] を読む）
- `--moment 0` （何番目のhighlight を使うか）
- `--source ~/delax-field-raw/DWT_EP001/raw/edit_master.mp4` （リポ外の編集済み素材）
- `--layout A` または `B`

出力:
- `episodes/{ID}/derivatives/{ID}_short_{moment_index}.mp4`

処理:
1. episode.yaml 読込
2. ソース動画を `highlight_moments[i].timestamp_sec` から `duration_sec` 秒切り出し
3. 16:9 → 9:16 reframe（center crop または smart crop）
4. レイアウトA/B でヘッダー帯・場所テロップ・サムネを overlay
5. ffmpeg で再エンコード

## YAML 拡張提案 (明日決める)

`episode.yaml` の `highlight_moments[]` に以下を追加すると render_short.py が自走しやすい:

```yaml
highlight_moments:
  - description: "アンダルシア人と猫の遭遇"
    timestamp_sec: 412
    duration_sec: 60
    suggested_platform: "shorts"
    # ↓ render_short.py 用の追加項目
    layout: "A"                 # A or B
    overlay_subtitle: "ペドレガレホの猫と"
    show_landmark: true         # 場所テロップを出すか
```

## 既知の Don't

- 縦動画にステッカー風ストライプ背景を入れない（街歩きの "場の空気" を壊す）
- カラオケ字幕や話者ピルは入れない（ナレ無しの矜持）
- BGM 自動挿入は当面しない（`creative.music_policy: "ambient-only"` を尊重）
- 田代/田淵/デラ などキャラ表現の移植は不可 (こっちは作家"デラ" 単独)
- `~/src/` 配下や `~/delax-field-raw/` などホーム直下に動画を置かない（→ 配置ポリシー参照）

## ファイル配置ポリシー (2026-04-27 確定)

撮影〜配信のファイルは役割で 3 層に分離する:

| 層 | 置き場 | 補足 |
|---|---|---|
| 撮影 raw (`.MP4` / `.insv`) | 外付け SSD のまま参照 | ローカル複製しない。ffmpeg は外付け直読みで十分 |
| 中間ファイル (reframe 出力等) | `/tmp/` or `~/src/_workdir/` | 作業中のみ、永続化しない |
| 最終生成物 (短尺 mp4 / サムネ) | `$DELAX_REPORTS_ROOT/delax-field-archive/<episode-id>/` | `~/Dropbox/delax-reports/` 系 (DELAX 共通規約) |

`render_short.py --output` 省略時は最終生成物の置き場に自動配信。
エピソード ID 未確定時は `_unsorted/` 配下。
