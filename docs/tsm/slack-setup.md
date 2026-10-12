# Slack: the 10-minute setup for the on-camera demo

Everything on Tacit's side is wired and tested. The three steps below are the ones only a workspace admin can do.

## 1. Create the app from the manifest (3 minutes)

1. Open https://api.slack.com/apps → **Create New App** → **From a manifest** → pick the workspace → paste `docs/slack-manifest.yaml` → Create.
2. **Install to Workspace** (OAuth & Permissions page) → copy the **Bot User OAuth Token** (`xoxb-…`).
3. **Basic Information → App-Level Tokens → Generate Token and Scopes** → name it `socket`, add scope `connections:write` → copy the token (`xapp-…`).

## 2. Put the two tokens in `api/.env` (1 minute)

```
TACIT_SLACK_BOT_TOKEN=xoxb-...
TACIT_SLACK_APP_TOKEN=xapp-...
TACIT_SLACK_CHANNELS=            # empty = every channel the bot is invited to; or comma-separated channel ids
TACIT_NOTIFY_SLACK_CHANNEL=      # optional: channel id where approval requests are posted
```

Then in Slack, invite the bot to the channel you will film: `/invite @Tacit`.

## 3. Give it history to learn from (5 minutes, optional but what makes the demo real)

Shadowing starts from the moment the bot connects. To have playbooks on day one, load the workspace export:

1. Workspace Settings → **Import/Export Data → Export** → Start Export (public channels; private channels need the admin plan).
2. Download the zip and run:

```bash
cd api && .venv/bin/python -m tacit.cli import-slack-export ~/Downloads/export.zip --window-h 6 --judge 10
```

This ingests the history, mines playbooks, and backtests them with the judge. No API calls, so Slack's rate limits do not apply.

## What the demo then shows (section 2 of the script)

1. Someone posts a trigger in the channel (an ask the history shows people answer the same way).
2. Tacit drafts a reply in shadow. The console's Shadow page shows the draft and, once a human answers, the judge's score.
3. For a job promoted to *propose*, the draft appears in the Inbox with a preview; approving it posts the reply in the thread.
4. The post carries an undo. Clicking it deletes the Slack message and logs the reversal.

## Verify before filming

```bash
cd api && .venv/bin/python -m tacit.cli doctor
```

The Slack line should read `connected … socket mode`. On `serve`, the log prints `socket mode connected` within a few seconds.
