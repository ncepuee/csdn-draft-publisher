<h1 align="center">CSDN Draft Publisher</h1>

<p align="center">An <a href="https://obsidian.md">Obsidian</a> plugin that syncs the current Markdown note to a <a href="https://www.csdn.net">CSDN</a> blog draft, and lets you manage existing drafts without leaving the vault.</p>

<p align="center">
  <img alt="Antigravity Code Support" src="https://img.shields.io/badge/Antigravity-Code_Support-4285F4?logo=google&amp;logoColor=white">
  <a href="https://gemini.google.com/"><img alt="Gemini 4 Carbon Agent" src="https://img.shields.io/badge/Gemini_4_Carbon-Agent_used%400.8.0-4285F4?logo=googlegemini&amp;logoColor=white"></a>
  <a href="https://github.com/ncepuee/csdn-draft-publisher"><img alt="GitHub stars" src="https://img.shields.io/github/stars/ncepuee/csdn-draft-publisher?logo=github&amp;cacheSeconds=86400"></a>
</p>

<p align="center">
  <a href="https://github.com/ncepuee/csdn-draft-publisher/releases"><img alt="Release" src="https://img.shields.io/github/v/release/ncepuee/csdn-draft-publisher"></a>
  <a href="https://github.com/ncepuee/csdn-draft-publisher/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/ncepuee/csdn-draft-publisher/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/ncepuee/csdn-draft-publisher/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/ncepuee/csdn-draft-publisher"></a>
</p>

## What it does

> **Full usage documentation lives in the [Wiki](https://github.com/ncepuee/csdn-draft-publisher/wiki)** — including a [中文快速上手指南](https://github.com/ncepuee/csdn-draft-publisher/wiki/%E4%B8%AD%E6%96%87%E4%BD%BF%E7%94%A8%E6%8C%87%E5%8D%97).

- Command palette: **Sync current note to CSDN draft**
- Ribbon icon menu: sync the current note, open the note in the CSDN editor, or open the draft manager
- Reads `title`, `description` / `summary`, `tags`, and `cover` / `image` from YAML frontmatter
- Automatically writes `csdn_article_id` back to frontmatter after creating a draft so re-syncing updates the same draft
- Optional Obsidian syntax preprocessing (`[[wikilinks]]`, `> [!callout]`, `%%comments%%`) while preserving fenced code blocks
- Draft manager panel: browse drafts of the active account (headless by default), search by title, paginate, import a draft for write-back editing, and delete drafts with confirmation
- Multi-account support: add, rename, delete, verify session, and clear login state per account with isolated Playwright profiles
- In-app QR code login modal (WeChat & CSDN App) without opening a separate browser window, with browser-window login kept as fallback
- Automation only looks for the "save draft" button; it never touches the publish button
- Local image references are detected and reported; images are not uploaded automatically

## How it works

The plugin ships a small Python bridge script (`csdn_bridge.py`, also embedded in `main.js` and released to the plugin folder on first run). When enabled, the plugin starts this script with the Python interpreter configured in the settings, and talks to it over local HTTP at `http://127.0.0.1:8765`. The bridge drives a [Playwright](https://playwright.dev/python/docs/intro) Chromium browser to fill the CSDN Markdown editor and save drafts.

## Privacy and data disclosure

- **No telemetry.** The plugin collects nothing and reports nothing.
- **No credentials stored.** The plugin never asks for or saves your CSDN username or password. Login happens once in a real browser window, and the session lives in a local Chromium profile under `%LOCALAPPDATA%\CSDN-Draft-Publisher\`.
- **Network use.** The bridge listens on `127.0.0.1` only and never sends your notes anywhere except to CSDN itself when saving a draft. Draft sync requires internet access to csdn.net.
- **Account required.** A CSDN account (and a one-time manual login per account profile) is required for the plugin to be useful.
- **Files outside the vault.** The plugin spawns a local Python process, writes `csdn_bridge.py` into its own plugin folder, and Playwright keeps browser login profiles under `%LOCALAPPDATA%\CSDN-Draft-Publisher\`. None of your vault notes are copied outside the vault.

## Setup

1. Install and enable the plugin.
2. Install Python 3.11+ and the bridge dependencies:

   ```bash
   pip install "playwright>=1.50.0"
   python -m playwright install chromium
   ```

   A conda environment works as well (`environment.yml` is provided).
3. Open the plugin settings and make sure **Python command** points to a Python that has Playwright installed (`python` by default, or a full path such as a conda env interpreter).
4. Turn on **Enable bridge service**. The plugin starts the local bridge automatically.
5. Run **Sync current note to CSDN draft**. On first run a browser window opens — log in to CSDN manually once; the session is reused afterwards.

## Settings

| Setting | Description |
| --- | --- |
| Bridge URL | Local bridge address, default `http://127.0.0.1:8765` |
| Enable bridge service | Starts the Python bridge with the configured interpreter; disabling only stops a bridge the plugin itself started |
| Python command | Python interpreter used to launch the bridge |
| CSDN accounts | Add, rename, log in, and clear login state per account; each account has its own browser profile |

If port `8765` is already served by a manually started bridge, the plugin reuses it and will not stop it when the toggle goes off.

## Recommended frontmatter

```yaml
---
title: My article title
description: One-sentence summary
tags:
  - Python
  - Obsidian
cover: https://example.com/cover.png
---
```

## Development

The repository root doubles as the plugin folder:

- `main.js` — plugin source (plain JavaScript, no build step). It embeds a base64 copy of the bridge script and writes it next to itself on first run.
- `csdn_bridge.py` — the Python bridge (source of truth for the embedded copy; regenerate the base64 constant when you change it).
- `manifest.json`, `versions.json` — plugin metadata for the Obsidian community directory.

Install a dev copy by symlinking or copying this folder to `<vault>/.obsidian/plugins/csdn-draft-publisher/` and reloading Obsidian.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the local check commands, branch and commit conventions, and how releases are cut ([RELEASE-CHECKLIST.md](./RELEASE-CHECKLIST.md)). Bug reports and feature requests use the issue templates; security issues go through [SECURITY.md](./SECURITY.md).

## License

[MIT](./LICENSE)
