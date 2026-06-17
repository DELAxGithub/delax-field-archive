# Field Telop — real local E2E runbook

機械(pipeline)は **synthetic full E2E で実走確認済み**（approve→runner→render_passage_short が実 1080×1920 mp4 + ffmpeg proxy を生成、overlay_sha SSoT 一致、source=registry://）。
**実 episode で 1 本通す**ために人間が用意するもの + 手順。

## 揃っているもの
- ✅ delax_core 0.3.4 wheel: `~/src/_worktrees/dvc-passage-info/dist/delax_video_core-0.3.4-py3-none-any.whl`
- ✅ ffmpeg / ffprobe（/opt/homebrew/bin）
- ✅ Dropbox root: `~/Dropbox/DELAX_field`
- ✅ registry template: `~/.config/delax-field-archive/field-shorts-sources.json`（**現在 sources 空**）

## 不足（人間が入れる）
```text
Missing:
- registry entry for <episode_id>            … 実 source path を登録（下記 1）
- source file path                           … 実撮影 mp4 の絶対パス
- DELAX_HMAC_SECRET (export, 非commit)        … 既存の HMAC secret を export（下記 2）
- base approved passage_v1 manifest          … <episode_id> の承認済み manifest（下記 3）
- pending job + overlay                      … Web 編集 or 手書き（下記 4）
```
> source path は捏造しない。実 path はユーザーのみが知る。

## 手順（実 E2E）

### 1. registry に実 source 登録
`~/.config/delax-field-archive/field-shorts-sources.json`:
```json
{ "version": 1, "sources": { "<episode_id>": "/abs/path/to/edit.mp4" } }
```

### 2. HMAC secret を export（値は commit/表示しない）
```bash
export DELAX_HMAC_SECRET='<既存の HMAC secret>'
```

### 3. base 承認済み manifest を用意
`<episode_id>` の passage_v1 manifest（source は `registry://<episode_id>` 推奨）を
`passage_v1.approve_passage_manifest()` で HMAC 署名 → `base_manifest.json`。
（Web fetch 用に render-queue の `field-telop/manifests/<episode_id>.json` にも置く＝`FIELD_MANIFEST_MOCK=0`）

### 4. overlay + pending job
Web（field-telop-check-web）で cue を編集 → overlay + pending job が作られる。
CLI のみで試すなら overlay/pending job を手書き（schema は field-telop-check-web / poller 参照）。

### 5. approve（HMAC 署名 + render-queue push）
```bash
cd ~/src/_worktrees/field-telop-poller
WHEEL=~/src/_worktrees/dvc-passage-info/dist/delax_video_core-0.3.4-py3-none-any.whl
DELAX_HMAC_SECRET="$DELAX_HMAC_SECRET" uv run --with "$WHEEL" --with pillow \
  python scripts/field_shorts/field_telop_approve.py \
    --job pending_job.json --overlay overlay.json --manifest base_manifest.json \
    --out-manifest approved_manifest.json --out-job approved_job.json \
    --approved-by <github-login> --push
```

### 6. runner dry-run（plan 確認・副作用なし）
```bash
uv run --with "$WHEEL" --with pillow python -m field_shorts.field_telop_runner --once
```

### 7. runner execute（実 render + proxy）
```bash
DELAX_HMAC_SECRET="$DELAX_HMAC_SECRET" uv run --with "$WHEEL" --with pillow \
  python -m field_shorts.field_telop_runner --execute --once
```

### 8. 成果物確認
- output mp4: `~/Dropbox/DELAX_field/field-telop/outputs/<episode_id>/<job_id>.mp4`
- proxy mp4: `~/Dropbox/DELAX_field/field-telop/proxies/<episode_id>/source_proxy.mp4`
- result: render-queue branch `field-telop/results/<job_id>.json`（status=done, overlay_sha, output_content_hash）

### 9. source 非露出 grep
```bash
gh api repos/DELAxGithub/delax-field-archive/contents/field-telop/results/<job_id>.json?ref=render-queue \
  --jq '.content' | base64 -d | grep -E '/Volumes/|/Users/' && echo "LEAK!" || echo "clean"
```

## hard stop（この runbook でも）
source 絶対パスを GitHub/Web/job/result に載せる / HMAC secret を Web/Vercel/GitHub に置く /
render_passage_short の approval check を弱める / dirty worktree に触る / main merge・PR・production deploy。
