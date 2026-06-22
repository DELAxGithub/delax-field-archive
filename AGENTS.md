# Agent Instructions

This repository is operated through multiple coding agents. Do not depend on
one vendor's chat history or proprietary command format.

For the GPS caption workflow, read:

- `docs/video-passage-pipeline.md`
- `scripts/video_passage_pipeline.py --help`

The `review.json` manifest is the source of truth. HTML is a visual review
artifact only. Never render or upload after editing an approved manifest;
run `validate`, regenerate the HTML, and `approve` again.

Do not commit raw video or audio files.
