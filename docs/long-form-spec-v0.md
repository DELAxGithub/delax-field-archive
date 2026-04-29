# DELAX 長尺街歩き YouTube 制作仕様 v0

**Status**: Draft (2026-04-27 起草) / 1本目テスト前
**Context**: delax-field-archive / 30-50分ノーカット街歩き (DWT/DBT 本編) / 1M views 狙い
**関連**: [short-render-spec.md](./short-render-spec.md) (9:16 ショート用、対の関係)

---

## 0. なぜ作るのか

DWT/DBT の本編 (5-15分) では **1M views ジャンルにアプローチできない** ことがリサーチで判明。
1M+ 取れる長尺街歩きは **30-75分のノーカット** が市場標準。
walktour-process の現行モード (16→6分編集) とは**別ジャンル**になるため、長尺専用パイプを設計する。

## 1. ターゲットフォーマット (リサーチ結論)

### 1-A. 採用する型: **B-Music 型** (Abao Vision 系)
- **ノーカット 30-50分** (将来 1時間+ も視野)
- **絵で勝つ** — 絶景postcard 級のロケーション選定が最重要
- **Lofi/Piano BGM 乗せ** (Storyblocks 経由、AI生成は monetization リスクで回避)
- **シリーズバッジ統一** (左下に小さく)
- **多言語 SEO** (JP/ES/EN)

### 1-B. リサーチ参照
リサーチ結果は別ファイル:
- [_research/maximiniano_nyc_HMWUygIW0o0/](../../../../Dropbox/delax-reports/delax-field-archive/_research/maximiniano_nyc_HMWUygIW0o0/) — 整備A型 2.25M
- [_research/qG4eO7doKbA/](../../../../Dropbox/delax-reports/delax-field-archive/_research/qG4eO7doKbA/) — 数撃ちB型 2.04M
- [_research/nomadic_ambience/](../../../../Dropbox/delax-reports/delax-field-archive/_research/nomadic_ambience/) — ASMR系 1.33M subs
- [_research/abao_vision/](../../../../Dropbox/delax-reports/delax-field-archive/_research/abao_vision/) — **Music系 258K subs / 1.6M view (採用モデル)**
- [_research/4k_japan/](../../../../Dropbox/delax-reports/delax-field-archive/_research/4k_japan/) — Tokyo反復型 143K subs
- [_research/gear_research_2026-04-27.md](../../../../Dropbox/delax-reports/delax-field-archive/_research/gear_research_2026-04-27.md) — 機材詳細

### 1-C. DELAX の独自武器
- **多言語ネイティブ JP/ES/EN** — 東京/NYC 系チャンネルが絶対真似できない領域
- **アンダルシア常駐** — 季節フック（Semana Santa, Feria, Sirocco）が撮れる
- **NHKラジオ畑の音楽センス** — BGM 選定/配置で差別化

## 2. 全工程と自動化マップ

| # | 工程 | 自動化 | 備考 |
|---|---|---|---|
| 1 | 撮影 (歩く) | ❌ 人間 | 絵を選ぶ感性が要 |
| 2 | SD 取り込み | ✅ **DELAX 既製** | `/sd-import-insta360` |
| 3 | (360時) リフレーム | △ 半自動 (Insta360 Studio) | 普段は Single Lens 4K60 でリフレーム不要 |
| 4 | 編集 | ✅ **不要** (ノーカット前提) | — |
| 5 | 章マーカー (14個) | ✅ 自動 | 時間ベース等間隔 + 人間がランドマーク命名 |
| 6 | 場所テロップ | ✅ DELAX 既製 | walktour-process バイリンガル機能流用 |
| 7a | BGM ライブラリ管理 | △ 半自動 | Storyblocks 月1 一括 DL → ローカルフォルダ |
| 7b | BGM 自動ミックス | ✅ 自動 | ffmpeg `acrossfade` + `loudnorm` |
| 8 | オープニング | ✅ テンプレ | フェードイン + ロゴ + 1フレ |
| 9 | エンディング CTA | ✅ テンプレ | 関連動画タイル + 登録誘導 |
| 10a | ffmpeg ProRes/HLG 直書き出し | ✅ 自動 | グレーディング不要回 |
| 10b | DaVinci 自動レンダ | ✅ 自動 | 色補正回、Resolve Python API |
| 11 | サムネ作成 | △ 半自動 | 候補10枚抽出 → 人選 → バッジ自動合成 |
| 12 | タイトル決定 | △ AI 候補 | Claude API で 5案生成 → 人選 |
| 13 | 説明欄テンプレ | ✅ 完全自動 | 撮影メタ + 14章 + 多言語タグ |
| 14 | 多言語字幕 (JP/ES/EN) | ✅ 自動 | Whisper + Claude/DeepL 翻訳 |
| 15 | YouTube アップロード | ✅ 自動 | YouTube Data API v3 |
| 16 | 多言語字幕投入 | ✅ 自動 | YouTube API |
| 17 | 公開時間スケジュール | ✅ 自動 | YouTube schedule API |
| 18 | ソーシャル展開 | △ 半自動 | Buffer or X API |

**人間タッチが要るのは 4 箇所** (撮影 / 章ランドマーク命名 / サムネ最終選択 / タイトル最終決定)

## 3. 機材設定 (リサーチ確定)

### 3-A. 撮影 (Insta360 X5)
- **デフォルト: Single Lens 4K60fps + FlowState ON** (リフレーム不要、即編集着手)
- **オプション: 8K 360 + Insta360 Studio reframe** (構図後決めしたい回のみ)
  - 注: 8K 360→ MegaView 170° で 4K相当、Linear 110° で **1440p に減衰**
- **InstaFrame は使わない** (中途半端で長尺向きじゃない)
- 連続撮影: 5.7K で 208分 / 8K で 65-86分 / マラガ夏季は 5.7K30fps へ落とす保険
- ストレージ: 8K 100Mbps 級 → 50分で 30GB+ 想定

### 3-B. YouTube アップロード (HLG HDR)
- コンテナ: HLG / Rec.2020 / 10bit / HEVC (= H.265 Main 10)
- HDR10/Dolby Vision は不要 (HLG が SDR 互換性で最有利)
- 視聴者の **5-15% しか実 HDR で見ない** (推測) けど、HLG なら SDR 自動変換が綺麗 → 見合う
- ffmpeg one-liner:
  ```
  ffmpeg -i input.mov -c:v libx265 -preset slow -crf 18 -pix_fmt yuv420p10le \
    -x265-params "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc:hdr-opt=1:repeat-headers=1" \
    -tag:v hvc1 -c:a aac -b:a 320k output_hlg.mp4
  ```
  `transfer=arib-std-b67` = HLG / `transfer=smpte2084` = PQ

### 3-C. 中間納品: ProRes (Adobe 不使用)
- DELAX は Adobe 解約方針 (プラッと037 で Whisper パイプラインへ完全移行済)
- ProRes 出力経路:
  - **A. ffmpeg `prores_ks` エンコーダで直書き出し** (高速、グレーディング不要回)
  - **B. DaVinci Resolve Python API でレンダリング** (色補正/Fusion テロップ必要回、プラッとパイプの knowhow 流用)
- フォーマット: ProRes 422 HQ (HLG メタデータ付き) を標準

### 3-D. BGM (カタログ駆動 — v0.3 で実装)

**選定原則 (Storyblocks 検索フィルタ):**
- Vocals なし (instrumental only)
- BPM 60-90 / Duration 2-5分 / Mood: Calm・Peaceful・Relaxed
- 避ける: Epic / Trap / EDM / Tropical House / 強パーカッション
- **Music Maker (Storyblocks AI生成) は使わない** (monetization リスク、Suno と同じ理由)
- 公式 API は Enterprise 限定 → Creator 契約では使えない

**Universal — 常時持っておく (ロケ場所問わず使える):**
- Lofi (`lofi hip hop`, `chill lofi`, `lofi beats calm`) **10-15曲**
- Solo Piano (`solo piano relaxing`, `peaceful piano`, `cinematic piano calm`) 8-10曲
- Ambient (`ambient calm`, `ambient cinematic`) 5-8曲

**Location-specific — ロケのたびに場所に合わせて DL:**
バックパッカー型運用なので、**毎回その街の文化的色合いに合った BGM を3-5曲ずつ追加**する。固定の地域別 Tier は持たず、撮影地が決まった段階で Storyblocks 検索:
- 例: マラガ/セビーリャ → Spanish Guitar / Flamenco Soft
- 例: パリ/リヨン → French Cafe Acoustic / Accordion Soft
- 例: リスボン → Fado Instrumental / Portuguese Guitar
- 例: ベルリン/ウィーン → Cinematic Piano / Soft Strings
- 例: ロンドン → Jazz Cafe Instrumental
- 例: モロッコ → World Acoustic / Oud Calm

`analyze_bgm.py` の自動振り分けは Universal 系 (lofi/ambient/cinematic/lounge/other) のみ対応。Location-specific のジャンル名は `mood_tag` 列に手動記入する運用 (例: `mood_tag: "spanish-guitar,andalusia"`)。

**ファイル配置とカタログ:**
```
~/src/_workdir/long-form-pipeline/bgm-library/
├── _inbox/          ← Storyblocks DL 直後の暫定置き場
├── _catalog.json    ← 自動生成 (analyze_bgm.py)
├── _catalog.csv     ← Excel で開ける版
├── _licenses/       ← Storyblocks ライセンス証明書 PDF (claim 防衛用)
├── lofi/
├── ambient/
├── cinematic/
├── lounge/
├── spanish-guitar/  ← Tier 2
└── bossa-nova/      ← Tier 2
```

**運用フロー:**
1. 月1〜2回、Storyblocks から DL → `_inbox/` に投げ込み
2. `scripts/analyze_bgm.py` 実行 → librosa で BPM / RMS / spectral_centroid / intro_silence_ms / outro_fadeout を抽出
3. ファイル名キーワードでジャンル自動判定 → `<genre>/` に振り分け
4. `_catalog.json` 更新

**カタログのスキーマ:**
| 列 | 用途 |
|---|---|
| `filename`, `path`, `storyblocks_id` | ID紐付け、license管理 |
| `genre` | mood マッチング |
| `duration_sec` | 動画尺マッチ選曲 |
| `bpm`, `key` | クロスフェード破綻防止 (近いBPM同士をつなぐ) |
| `rms_mean`, `spectral_centroid_hz` | 明暗・音圧の判別 (朝・夕方マッチ) |
| `intro_silence_ms` | 1500ms以上は acrossfade で違和感、選曲から除外 |
| `outro_fadeout` | フェードアウト済み曲の判別 |
| `mood_tag` | 手動列 (calm/mellow/hopeful 等、必要に応じて) |

**レンダ時の選曲ロジック (`render_long.py --bgm-genre lofi[,ambient]`):**
- カタログから genre フィルタ → `intro_silence_ms < 1500` で絞り込み
- ランダムシャッフル (`--bgm-seed` で再現可能)
- 動画尺満たすまで曲追加、不足なら同じ集合をループ
- ffmpeg `acrossfade=d=5:c1=tri:c2=tri` で連結 → `loudnorm=I=-16:TP=-1.5:LRA=11` 正規化
- v0.3 は BGM のみ (環境音オフ)。混ぜる戦略は試聴後に判断

**Suno は使わない** (YouTube monetization リスク + RIAA 訴訟係争中)。

### 3-E. 中間ファイル管理 (50分尺で 数百GB対策、最初から組込む)

ProRes 422 HQ は **50分尺で 200-400GB** に達する。HEVC 完成 / YouTube アップロード完了をトリガーにクリーンアップを必須実装する。

**運用ルール:**
1. ProRes 中間ファイルは `~/src/_workdir/long-form-pipeline/output/_prores/<episode-id>/` に書き出し
2. 完成 H.265 HLG mp4 が `$DELAX_REPORTS_ROOT/delax-field-archive/<episode-id>/` に存在することを確認
3. YouTube アップロード成功 (動画 ID 取得) を確認
4. 上記 2-3 が揃った時点で ProRes 中間ファイルを **自動削除** (デフォルト) / **アーカイブ** (オプション)

**アーカイブ先候補 (将来):**
- AWS S3 Glacier Deep Archive ($1/TB/月)
- Backblaze B2 ($6/TB/月、API シンプル)
- Dropbox は容量プランが見合わず却下

**MVP 実装方針:**
- `render_long.py --cleanup-prores` フラグ付きなら、HEVC 書き出し成功直後に ProRes を削除
- YouTube アップロード含む full pipeline では、アップロード成功フックで削除
- デフォルトは **保管** (ユーザーが意識的に削除許可するまで残す)

## 4. ガワデザイン仕様

### 4-A. サムネ (絵で勝つ哲学 / Abao 系)
- 絵: 絶景 postcard 級 — 透視構図 / 自然光 / 色の鮮やか / シメトリー
- テキスト: **左下に小さなシリーズバッジのみ**
- 大きいキャプション禁止 (Maximiniano 風の「NEW YORK 8AM」は避ける)
- シリーズバッジ:
  - 文言: 「DELAX」 or 「ANDALUSIA 4K HDR」 (検討中)
  - フォント: コンデンスドゴシック (Bebas Neue or Anton)
  - 配置: 左下、半透明白背景の角丸
- 抽出元: 動画から 10-15 枚自動抽出 → 人が 1枚選ぶ → スクリプトがバッジ合成

### 4-B. タイトルテンプレ
- 構文: `[シーン記述] / 4K HDR / [音楽ジャンル]` (Abao 模倣)
- 例:
  - `Costa del Sol Sunset Drive: Marbella to Málaga / 4K HDR / Relaxing Piano`
  - `Andalusian White Village: Frigiliana Walking Tour / 4K HDR / Spanish Guitar`
  - `Málaga Old Town Night Walk: Tapas Quarter / 4K HDR / Calm Lofi Beats`
- **「8K」は使わない** (実質 4K 以下、誇大広告判定回避)

### 4-C. 説明欄テンプレ (Maximiniano 模倣)
```
[1行フック: シーン描写の問いかけ]

[2行目: 経路ディテール、尺、天候]

[3行目: 何が見えるか具体描写]

🗓️ Filmed: [日付] | [曜日] | [時間] | ☀️ [天気]
🎧 No narration | Subtitles available in JP/ES/EN

[14章タイムスタンプ]

[CTA: Like / Subscribe / Thanks]

#[3-5 ハッシュタグ]
```

### 4-D. 章マーカー
- 14個前後 (Maximiniano 標準)
- 3-7分間隔
- ランドマーク名 (英語+ローカル名併記推奨)
- 例: `12:34 Plaza de la Merced / メルセー広場`
- 自動化: 時間ベース等間隔 14分割 → タイムコード生成 → **人間がランドマーク命名 UI** (Claude Code 内で対話)

### 4-E. 場所テロップ (画面 overlay) — v0.2 改修
- バイリンガル地名テロップ (NHKふれあい街歩き 文法、walktour-process と方針共通)
- **フェード in: 1.0s / hold: 6.5s / fade out: 0.8s** (合計 ~8.3s)
- **半透明黒帯 alpha 200/255** (明るい背景 = 旧港の青空でも字が浮かない濃さ)
- **フォント統一: ヒラギノ丸ゴ ProN W4** (バッジと同じ系統で「ゆるめ」のブランド統一)
- PRIMARY 240px / SECONDARY 76px / halo offset 6px (太字相当の存在感)
- 章の頭 (タイムコード) で出す案は将来検討、v0.2 ではオープニング1回のみ
- safe zone: 4K の画面下三分の一 (y=CANVAS_H-540 起点)

### 4-F. オープニング 0:00-9.8 (v0.2 改修 / 重要)

**狙い**: YouTube サムネをタップしてからの最初の 1〜2 秒で「美しい絵」がスクロールの手を止める。シリーズロゴと場所テロップは絵を邪魔しない透かしとして後から差し込む。

| 時刻 | 演出 |
|---|---|
| 0:00-0:01 | **絶景の歩行シーンだけ** (テロップなし、バッジなし) — 視覚で掴む |
| 0:01-0:02 | シリーズバッジ「デラさんぽ 4K」が左下に **fade in** (1秒) |
| 0:01.5-0:02.5 | 場所テロップが画面下部に **fade in** (1秒) |
| 0:02.5-0:09.0 | 場所テロップ hold (6.5秒) |
| 0:09.0-0:09.8 | 場所テロップ **fade out** (0.8秒) |
| 0:09.8 以降 | バッジのみ常時表示 |
| BGM | 1曲目の頭から **fade in** (1秒) |

**絶景フレーム選定**: 撮影者が動画頭に最も惹きの強いカットを置く運用 (人間判断、Step 4 サムネ抽出で AI 補助案あり)。

### 4-G. エンディング CTA
- 終了 30秒前から: 関連動画タイル overlay (左下 or 右下)
- 最後 5秒: 「Subscribe」テロップ + チャンネルロゴ
- BGM: フェードアウト (3秒)

### 4-H. シリーズ統一感
- 全動画で同じ位置・フォント・配色のバッジ
- 全動画で同じオープニング・エンディングテンプレ
- 全動画で同じ場所テロップデザイン
- 全動画で同じ説明欄構造

## 5. ファイル配置 (3層分離 / 既存ポリシー準拠)

| 層 | 配置 | 補足 |
|---|---|---|
| 撮影 raw | 外付け SSD のまま参照 | コピーしない、ffmpeg 直読み |
| 中間ファイル | `~/src/_workdir/long-form-pipeline/` | source/ output/ bgm-library/ で分離 |
| 最終生成物 | `$DELAX_REPORTS_ROOT/delax-field-archive/<episode-id>/` | YouTube アップ後の保管 |
| BGM ライブラリ | `~/src/_workdir/long-form-pipeline/bgm-library/lofi/` 等 | 将来 Dropbox 共有検討 |
| リサーチ資料 | `$DELAX_REPORTS_ROOT/delax-field-archive/_research/` | 完了済 |

## 6. CLI 設計

```bash
# BGM カタログ生成 (Storyblocks DL 後に1回)
scripts/analyze_bgm.py
# → bgm-library/_inbox/*.mp3 を解析、ジャンル別に振り分け、_catalog.json 出力

# 基本: ノーカット長尺レンダ (v0.3 実装済)
scripts/render_long.py \
    --source <reframed.mp4> \
    --episode-id DWT_EP002 \
    --location-primary "マラガ" \
    --location-secondary "Málaga, España · 2026.04.27" \
    --shoot-date 2026-04-27 \
    --chapter-count 14 \
    --bgm-genre lofi,ambient \
    --bgm-seed 42 \
    --output-format hlg-hevc       # or hlg-prores422hq / sdr-h264

# サムネ候補抽出 (未実装、Step 4)
scripts/extract_thumb_candidates.py \
    --source <reframed.mp4> \
    --count 12 \
    --output-dir <out>/thumbs/

# 説明欄生成 (未実装、Step 5)
scripts/generate_description.py \
    --episode-id DWT_EP002 \
    --chapters chapters.txt \
    --shoot-meta meta.yaml \
    --output description.txt
```

## 7. 実装ロードマップ

| 順 | モジュール | 状態 | 備考 |
|---|---|---|---|
| **1** | **ffmpeg ノーカット書き出し** (SDR/HLG HEVC/ProRes 422 HQ) | ✅ 完了 (v0.1) | `render_long.py --output-format` |
| **2** | 章マーカー + 場所テロップ overlay + シリーズバッジ | ✅ 完了 (v0.2) | fade timing 込み |
| **3a** | BGM カタログ生成 (`analyze_bgm.py`) | ✅ 完了 (v0.3) | librosa + ジャンル自動振り分け |
| **3b** | BGM 自動ミックス (acrossfade + loudnorm、カタログ駆動) | ✅ 完了 (v0.3) | `--bgm-genre lofi[,ambient]` |
| 3c | HLG 出力の実機確認 (現状 sdr-h264 のみ動作確認) | 🟡 要確認 | `--output-format hlg-hevc` の挙動再確認 |
| **4** | **サムネ候補抽出** (`extract_thumb_candidates.py`) | ✅ 完了 (v0.4) | 12枚 + バッジ合成 + preview.jpg |
| **5** | **説明欄生成** (`generate_description.py`) | ✅ 完了 (v0.4) | episode.yaml + chapters → JP/ES/EN |
| **6** | **多言語字幕生成** (`generate_subtitles.py`) | ✅ 完了 (v0.4) | mlx-whisper + Claude API 翻訳 |
| **7** | **YouTube API アップロード** (`upload_youtube.py`) | ✅ 完了 (v0.4) | 動画 + サムネ + 字幕 + プレイリスト + 予約公開 |
| 8 | 章名命名 UI (placeholder→ランドマーク名) | ⬜ 未着手 | 4-D 仕様、人間対話 |
| 9 | extract_metadata.py (GPS/weather/EXIF 自動取得) | ⬜ 未着手 | episode.yaml の geo/weather/capture 自動化 |
| 10 | DaVinci 自動レンダ (色補正回 option) | ⬜ 未着手 | プラッと037 API 流用、後回し可 |
| 11 | **中間ファイルクリーンアップ機構** (ProRes 自動削除 / アーカイブ) | ⬜ 未着手 | Step 7 のフックに統合、必須 |

**MVP = 1〜3 完了 (v0.3)、フルスタック = 4〜7 完了 (v0.4)**。
- レンダフロー: `/field-render` (1〜3 を統合)
- 公開フロー: `/field-publish` (4〜7 を統合)

次の優先度: **3c (HLG 検証) → 9 (メタデータ自動化) → 8 (章名命名)** の順を想定。

## 8. 既存ツールとの関係

- **walktour-process v1** (16→6分編集モード): 残す。短編向けはこっち。
- **walktour-process v2** (将来): long-form モード追加で本仕様を吸収する案。ただし v0 段階では別スクリプト `render_long.py` で先行実装し、安定したら統合。
- **render_short.py** (9:16 ショート 30秒): 残す。長尺と短尺は完全に別パイプ。
- **/sd-import-insta360**: そのまま流用、変更不要。
- **プラッと037 Whisper パイプライン**: DaVinci Python API のコードを Step 8 で流用。

## 9. 1本目テスト計画

**素材**: `~/src/_workdir/long-form-pipeline/source/マルセイユ.mp4` (16分8秒、4K HEVC、25Mbps)
- ProRes ではないが、**MVP 動作確認には十分**
- 16分 = 30-50分の 1/3 だが、パイプライン検証用としてOK
- マルセイユ素材なので場所テロップは "Marseille / マルセイユ · [仮日付]"

**目標**: ステップ 1〜3 完了で、HLG HDR + 章マーカー + 場所テロップ + BGM ミックス が乗った 16分動画を出す
- 出力先: `~/src/_workdir/long-form-pipeline/output/marseille_test_v0.mp4`
- 検証ポイント:
  - HLG メタデータが正しく入ってるか (ffprobe で確認)
  - 章マーカーが時間通りに出るか
  - 場所テロップ overlay の位置・フォント
  - BGM ミックスのクロスフェードが破綻しないか
  - 全体音量バランス (BGM が小さすぎ/大きすぎないか)

**BGM ライブラリ**: 1本目テスト前に Storyblocks から Lofi 5-10曲 DL 必要 (ユーザー手動)

## 10. 決定事項 / オープン項目

### 決定済 (2026-04-27)
| 項目 | 決定 |
|---|---|
| **シリーズバッジ文言** | **「デラさんぽ 4K」** |
| **フォント** | **ゆるめ (ヒラギノ丸ゴ ProN W4 系)** |
| **バッジ色味** | **単色黄色** (背景 #FFC800 半透明、文字は濃いブラウン #281E00) |
| 1本目シリーズコード | **TEST_marseille_2026-04-02** (テスト用、適当) |
| 1本目場所 | マルセイユ (Marseille) |
| 1本目撮影日 | 2026-04-02 |

### 未定 (今後)
| 項目 | 候補 |
|---|---|
| 公開ペース目標 | 月3本 / 月5本 / 月8本 |
| 本番シリーズコード体系 | DWT_EP002 / DLF_EP001 / 別系統 |
| ロケハン優先順位 | Frigiliana / Mijas / Pedregalejo / Ronda / Setenil |

---

## Changelog

- **2026-04-27 v0** 起草 (リサーチ 5チャンネル + 機材エージェントレポ完了後)
- **2026-04-27 v0.1** バッジ「デラさんぽ 4K」/ ゆるめ丸ゴ / 単色黄色 / 1本目はマルセイユテスト (TEST_marseille_2026-04-02) で決定
- **2026-04-27 v0.2** マルセイユ 1stレンダ後フィードバック反映:
  - 4-E: 場所テロップ alpha 140→200、フォント丸ゴ統一、PRIMARY 192→240、halo offset 6
  - 4-F: オープニング演出を「絶景先 → 1〜2秒で透かしフェードイン」に再設計
  - 3-E: ProRes 中間ファイル管理セクション新設 (50分尺 数百GB対策、最初から組込む)
  - Step 9: クリーンアップ機構をロードマップに追加
- **2026-04-27 v0.5** ショート量産フロー追加:
  - `scripts/render_short.py` v2: 末尾 N秒 CTA overlay (`--cta-text "Full Tour →"`) 対応、PNG を `-loop 1 -framerate` で連続フレーム化して fade filter 動作
  - `scripts/generate_shorts_caption.py` 新設: episode.yaml + 本編 URL → YouTube Shorts / Instagram Reels / TikTok 別キャプション一括生成 (動画ファイルは1本で3プラットフォーム使い回し)
  - `scripts/upload_youtube.py` v2: `--kind shorts` で `episode.yaml` の `publish.shorts.youtube` に保存 (本編 URL を上書きしない)
  - `/field-shorts` スキル新設 (`/field-publish` とは別、独立タイミング・複数本切り出し対応)
  - マルセイユ Le Panier 路地シーン (t=829-859) で 30秒 Shorts 1本目アップロード成功 → https://youtu.be/isHdcKddMfk
  - 既知: `defaultAudioLanguage=zxx` (ISO 639-2 3文字) は API 400 で拒否される。`ja` で送信して Studio 後付け変更が現実的
  - IG/TikTok 自動アップロードは実装見送り (Meta API ハードル高、TikTok Business API 審査要、X API 有料化 $200/月〜)。ファイル + キャプション一式準備で手動 5分が現実解
- **2026-04-27 v0.4.2** API/サブスク方針確定:
  - `generate_description.py`: デフォルトを **テンプレのみ** に反転 (`--no-llm` → `--polish-with-llm` 反転)
  - 理由: Claude Pro/Max サブスクとは別課金になる Anthropic API を常用しない方針。polish が欲しい時は Claude Code 内で手動依頼
  - `field-publish.md` スキルにも同方針を明記
  - YouTube Data API v3: tacchiradio@gmail.com で有効化済 (2026-04-27)
- **2026-04-27 v0.4.1** 運用調整:
  - 3-D: BGM の Tier 2/3 (アンダルシア固定 / 差し色) 廃止 → 「Universal + ロケ場所別 ad-hoc DL」に変更 (バックパッカー型運用に整合)
  - YouTube アカウント: tacchiradio@gmail.com 運営、Google Cloud OAuth は同アカウントで発行
  - `upload_youtube.py`: `--print-auth-url` フラグ追加 (Firefox 等任意ブラウザで認可可能に)
  - 注意: `ANTHROPIC_API_KEY` は Claude Pro/Max サブスクとは別課金 (従量)。サブスク内完結したいなら `--no-llm` でテンプレ運用 or Claude Code 内で手動 polish
- **2026-04-27 v0.4** フルスタック化 (Step 4〜7):
  - `scripts/extract_thumb_candidates.py` (4): フレーム抽出 + バッジ合成 + preview.jpg
  - `scripts/generate_description.py` (5): episode.yaml + chapters → 多言語説明欄 (JP/ES/EN、Claude API オプション)
  - `scripts/generate_subtitles.py` (6): mlx-whisper 文字起こし + Claude API 翻訳 (--no-subtitles でスキップ可)
  - `scripts/upload_youtube.py` (7): YouTube Data API v3、動画+サムネ+字幕+プレイリスト+予約公開、credentials は `~/.config/delax-field-archive/`
  - `/field-publish` スキル新設 (4〜7 を一気通貫)
  - `episode.yaml` の publish 欄を upload 後に自動更新
  - 既知の制約: メタデータ自動取得 (Step 9)、HLG 実機検証 (3c)、章名命名 (Step 8) は未着手
- **2026-04-27 v0.3** BGM カタログ駆動の実装完了:
  - 3-D: 「ランダム選曲」→「カタログ駆動 + intro_silence フィルタ + シャッフル」に書き換え
  - 新規: `scripts/analyze_bgm.py` (librosa + ffprobe で 23曲解析、ジャンル別振り分け済)
  - `render_long.py` v0.3: `--bgm-genre`, `--bgm-seed`, `--no-bgm` 追加 / acrossfade 連結 + loudnorm
  - Storyblocks 24曲 (1曲重複削除して 23曲) を `bgm-library/{lofi,ambient,cinematic,lounge,other}/` に分類済
  - 既知の課題: HLG 出力経路は v0.3 では未検証 (3c)、章名は placeholder のまま (Step 8)
