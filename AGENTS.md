# Agent Instructions

This repository is operated through multiple coding agents. Do not depend on
one vendor's chat history or proprietary command format.

For the GPS caption workflow, read:

- `~/work/ambient/bike-tour/local/docs/video-passage-pipeline.md`（自転車ルートとして2026-11-16に移設）
- `~/work/ambient/bike-tour/local/scripts/video_passage_pipeline.py --help`（移設済み）

The `review.json` manifest is the source of truth. HTML is a visual review
artifact only. Never render or upload after editing an approved manifest;
run `validate`, regenerate the HTML, and `approve` again.

Do not commit raw video or audio files.
