# im8-brief-bot — DEPRECATED

This bot has been **consolidated into `im8-production-bot`**.

## Why

The brief bot did a subset of what the production bot already does. Maintaining two separate Telegram bots for the same workflow added unnecessary complexity.

## What replaced it

All brief parsing, row generation, and sheet writing is now handled by `im8-production-bot`:

- `/brief [concept]` — generates a full brief with hook scores
- `hold` — stages the row to your private staging sheet with a paste-ready row
- `send [editor]` — stages + dispatches to Slack in one step
- `/improve [note]` — logs feedback for the autoresearch loop

## Migration

1. Stop the `im8-brief-bot` Railway service (or set it to inactive)
2. All functionality is live in `im8-production-bot`
3. The staging sheet (set via `STAGING_SHEET_ID` env var) replaces the direct editor sheet write

## Staging sheet setup

1. Create a new private Google Sheet for yourself
2. Copy the Sheet ID from the URL
3. Set `STAGING_SHEET_ID=your_sheet_id` in the `im8-production-bot` Railway environment variables
4. The bot will auto-create headers on first `hold`

---

*Deprecated: April 2026*
