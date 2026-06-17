# Field Telop poller — setup & LaunchAgent template

field-telop-check-web が render-queue ブランチに積む job/overlay を読み、Passage
telop の実写レンダーを段取りする **field 専用 runner**（tachi poller に相乗りしない、
別 LaunchAgent）。queue 検証 = `scripts/field_shorts/field_telop_queue_poller.py`、
queue I/O = `field_telop_queue.py`、orchestration = `field_telop_runner.py`、
再承認 = `field_telop_approve.py`。

> ⚠️ **Phase 7 runner 実装済み**（`field_telop_runner.py`: `--dry-run` default /
> `--execute` / `--once` / `--loop`）。**`--dry-run` は queue 書込も subprocess もしない**。
> 実 GitHub write / 実 render は `--execute` 明示時のみ（delax_core wheel + DELAX_HMAC_SECRET +
> ffmpeg + 実 source 登録が必要）。LaunchAgent 登録・常駐開始は**まだしない**（人間が手動で）。
> 単一 Mac runner 前提（claim は running 書込→approved-ready 削除の順、厳密 lease 競合は未対応）。
>
> ⚠️ **production 化前に** `feat/field-passage-integration`（render_passage_short.py /
> field_shorts/* / passage_v1 の在処）を delax-field-archive main か基準ブランチへ統合すること。

## 1. ローカル setup（人間が実施）

### 1.1 source registry（D6 allowlist）

`~/.config/delax-field-archive/field-shorts-sources.json`:

```json
{
  "version": 1,
  "sources": {
    "DBT_EP003": "/Volumes/Insta360/DBT_EP003/edit_master.mp4"
  }
}
```

- `episode_id → 絶対 source path`。**git に入れない**。未登録 episode は fail-closed（`SourceNotAllowed`）。
- テンプレ（空 `sources`）は作成済み。実 path は素材確定後に登録する。

### 1.2 Dropbox proxy root

- `~/Dropbox/DELAX_field/field-telop/proxies/` 作成済（git 非追跡）。
- poller が `episode_id` から `/DELAX_field/field-telop/proxies/<episode_id>/source_proxy.mp4` を出力。

### 1.3 delax_core wheel

- overlay_sha 実算出 / render に必須（`render_passage_short` が import 時 hard-require）。
- wheel: `delax_video_core-0.3.4-py3-none-any.whl`（`~/src/_worktrees/dvc-passage-info/dist/`）。
- 実行は `uv run --with <wheel> --with pillow python ...`。

## 2. LaunchAgent テンプレ（自動登録しない）

`~/Library/LaunchAgents/com.delax.field-telop-poller.plist`（**コピー・登録は人間が手動で**）:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>            <string>com.delax.field-telop-poller</string>
  <key>WorkingDirectory</key> <string>/Users/delaxpro/src/_worktrees/field-telop-poller/scripts</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <!-- runner entrypoint (--loop) is NOT yet implemented; placeholder command -->
    <string>uv run --with /ABS/PATH/delax_video_core-0.3.4-py3-none-any.whl --with pillow python -m field_shorts.field_telop_runner --execute --loop</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <!-- set real values here; this plist is NOT committed -->
    <key>DELAX_HMAC_SECRET</key>     <string>__SET_ME__</string>
    <key>GITHUB_PAT</key>            <string>__SET_ME__</string>
    <key>GITHUB_REPO_OWNER</key>     <string>DELAxGithub</string>
    <key>GITHUB_REPO_NAME</key>      <string>delax-field-archive</string>
    <key>DROPBOX_APP_KEY</key>       <string>__SET_ME__</string>
    <key>DROPBOX_APP_SECRET</key>    <string>__SET_ME__</string>
    <key>DROPBOX_REFRESH_TOKEN</key> <string>__SET_ME__</string>
    <key>DROPBOX_ROOT</key>          <string>/DELAX_field</string>
  </dict>
  <key>StandardOutPath</key>  <string>/Users/delaxpro/Library/Logs/field-telop-poller.out.log</string>
  <key>StandardErrorPath</key><string>/Users/delaxpro/Library/Logs/field-telop-poller.err.log</string>
  <key>RunAtLoad</key>        <false/>          <!-- manual start only -->
  <!-- NOTE: once bootstrap'd, StartInterval makes launchd poll every 120s even
       without a manual start. Only register this AFTER the runner is implemented. -->
  <key>StartInterval</key>   <integer>120</integer>
</dict>
</plist>
```

### 手動登録（runner 実装後に人間が実行 — 今はしない）

```bash
# save the plist block above to a file, fill the __SET_ME__ values, then:
cp /path/to/com.delax.field-telop-poller.plist ~/Library/LaunchAgents/com.delax.field-telop-poller.plist
# 値を埋めてから:
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.delax.field-telop-poller.plist
launchctl kickstart -k gui/$(id -u)/com.delax.field-telop-poller
# 停止:
launchctl bootout gui/$(id -u)/com.delax.field-telop-poller
```

> Phase 5 では `launchctl bootstrap` を実行しない（常駐開始しない）。secrets を含む plist は commit しない。

## 3. poller の責務（実装済み = dry-run builders）

`parse_job` / `parse_overlay`（strict key allow-list, 数値厳格化）/ `assert_job_overlay_consistent` /
`assert_manifest_match`（approved + content_hash + passage_info_hash + design_sha 再検証）/
`apply_overlay` / `compute_overlay_sha`（`render_passage_short.overlay_sha` 遅延 import = SSoT、再実装なし）/
`build_render_passage_job` / `build_render_command`（`--registry` 経由、source 非載せ）/
`proxy_dropbox_path` / `build_proxy_command`（`field_shorts.proxy.build_proxy_cmd` 再利用）/
`build_result`（overlay_sha / output hash / status、source 非載せ）/ `assert_source_registered`（未登録 fail-closed）。

## 3a. runner（Phase 7、実装済み）

```bash
# dry-run（default・安全。queue 書込も subprocess もしない。1 pass）
uv run --with <wheel> --with pillow python -m field_shorts.field_telop_runner --once

# 実 render（要 DELAX_HMAC_SECRET + 実 source 登録 + ffmpeg）
DELAX_HMAC_SECRET=... uv run --with <wheel> --with pillow \
  python -m field_shorts.field_telop_runner --execute --once   # or --loop
```
- approved-ready job のみ処理（`is_render_eligible`）。pending は無視。
- approved manifest を `manifests-approved/<ep>/<content_hash>` から取得 → `assert_manifest_match`。
- `render_passage_short.py`(subprocess) が overlay_sha/HMAC を最終検証（runner は委譲・再署名しない）。
- proxy は local Dropbox mount へ ffmpeg 出力（自動同期）。result を `field-telop/results/<job_id>.json` へ。
- 失敗時 failed 遷移（stuck running なし）、error は絶対パス redact（source 非露出）。

## 3b. approve → render-queue（Gap A）
`field_telop_approve.py --push` で approved manifest + approved-ready job を render-queue へ。
source は registry:// allowlist + denylist で fail-closed。

## 4. HMAC 再承認フロー（Phase 6 で確定・解決済み）

web 編集は cue を変えるので、`render_passage_short`（`job.overlay_sha == overlay_sha(manifest 内 cue)`
＋ HMAC 承認 content_hash 一致を要求）に渡す前に **編集反映 manifest の再承認(HMAC 再署名)** が要る。
これは **local approve CLI `scripts/field_shorts/field_telop_approve.py`** が担う（Web/Vercel/poller は
署名しない）。

```bash
DELAX_HMAC_SECRET=... uv run --with <delax_core 0.3.4 wheel> --with pillow \
  python scripts/field_shorts/field_telop_approve.py \
    --job pending_job.json --overlay overlay.json --manifest base_manifest.json \
    --out-manifest approved_manifest.json --out-job approved_job.json \
    --approved-by <github-login>
```

処理: pending job/overlay/base manifest 整合確認 → overlay を cue に適用 → **source を
`registry://<episode_id>` に sanitize**（絶対パスを GitHub-bound artifact に残さない。allowlist +
denylist 二重 fail-closed）→ approval draft reset → `passage_v1.validate_passage_manifest` →
`passage_v1.approve_passage_manifest`（HMAC 署名、**唯一の署名経路**）→ `verify_approval` →
`render_passage_short.overlay_sha`(SSoT) で overlay_sha 算出 → job を **approved-ready** に更新
（新 content_hash + overlay_sha + approver meta）。

### state 遷移
```
pending (Web, overlay_sha なし)  ──approve CLI(人間+secret)──▶  approved-ready  ──poller──▶ running ─▶ done/failed
```
- poller は **`is_render_eligible`（status==approved-ready）のみ render**。pending は render しない。
- `DELAX_HMAC_SECRET` 不在 → approve も verify も fail-closed。
- **残る real-render 前提**（hard stop ではないが必要）: source registry 登録 + delax_core wheel + 実 manifest 配置。
