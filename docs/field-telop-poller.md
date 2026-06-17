# Field Telop poller — setup & LaunchAgent template

field-telop-check-web が render-queue ブランチに積む job/overlay を読み、Passage
telop の実写レンダーを段取りする **field 専用 poller**（tachi poller に相乗りしない、
別 LaunchAgent）。SSoT は `scripts/field_shorts/field_telop_queue_poller.py`。

> ⚠️ **Phase 5 時点は dry-run（コマンド組立まで）**。実 GitHub render-queue I/O・実 ffmpeg・
> 実 Dropbox upload・polling loop の常駐 entrypoint（`--loop`）は未実装。下記 LaunchAgent は
> **scaffold（テンプレ）**で、runner 実装後に有効化する。**今は自動登録しない**。
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
    <string>uv run --with /ABS/PATH/delax_video_core-0.3.4-py3-none-any.whl --with pillow python -m field_shorts.field_telop_queue_poller --loop</string>
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

**未実装（runner）**: polling loop / 実 GitHub branch I/O / 実 ffmpeg 実行 / 実 Dropbox upload /
編集済み manifest の HMAC 再承認（real render の前提、下記）。

## 4. real render 前の未解決点（hard stop）

`render_passage_short` は `job.overlay_sha == overlay_sha(manifest_cue)`（**manifest 内の cue** に対して）
かつ HMAC 承認済み `content_hash` 一致を要求する。web 編集は cue を変えるので、real render の前に
**編集を反映した manifest を再承認（HMAC 再署名）** する必要がある。誰が・どう再承認するか（人間の
再レビュー or 自動）は未確定。**poller は勝手に HMAC 再署名しない**（承認ゲートを弱めるため）。
ここが決まり、source registry 登録 + delax_core wheel が揃うまで real render はしない。
