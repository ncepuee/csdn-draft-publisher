# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).
Release tags use the exact manifest version (`0.6.1`, not `v0.6.1`) as required
by the Obsidian community directory.

## [Unreleased]

## [0.8.0] - 2026-11-26

### Added

- Built-in QR code login modal (`QrLoginModal`) directly inside Obsidian,
  supporting both WeChat and CSDN App QR code sign-in without popping up a
  browser window.
- Safe re-scan / account-switch prompt when an account already has a valid CSDN
  session (`already_logged_in`), preserving existing cookies unless the user
  explicitly chooses to re-scan.
- QR login endpoints in `csdn_bridge.py` (API `0.7.0`):
  `POST /login/qr/start`, `GET /login/qr/status`, `POST /login/qr/refresh`,
  and `POST /login/qr/cancel`, plus automatic Draft Box refresh upon login.
- Quick QR login entry points in account settings, the Draft Box toolbar, the
  command palette, and the ribbon menu, plus a one-click "Install browser
  kernel" button in settings.

### Fixed

- Prioritized full desktop Chrome / Microsoft Edge in headless mode to avoid
  CSDN gateway `ERR_CONNECTION_CLOSED` drops triggered by
  `chrome-headless-shell` when authentication cookies are present, and provided
  automatic browser fallback when Playwright's bundled Chromium is not
  installed.
- Parsed CSDN's `/article/list` JSON response directly for reliable draft
  listing, filtered out hidden `[role="tab"]` elements that caused 180-second
  timeouts on `mp.csdn.net`, and failed fast when unauthenticated.
- Validated real CSDN authentication cookies (`UserToken` & `UserName`) instead
  of relying on unauthenticated editor DOM controls.
- Fixed `getBridgeScriptPath()` resolving `this.manifest.dir` as a relative
  path instead of joining it with the vault's `adapter.basePath`.

## [0.7.0] - 2026-11-25

### Added

- Automatic `csdn_article_id` and `csdn_account_id` frontmatter write-back after
  creating a new draft, preventing duplicate drafts on subsequent syncs.
- Optional Obsidian Markdown syntax preprocessing before sync (strips `%%...%%`
  comments, converts `[[wikilinks]]` and `> [!callout]` headers while preserving
  fenced code blocks).
- Account rename and delete actions in settings, plus real headless session
  verification via `/session?verify=1`.
- Dedicated `styles.css` stylesheet replacing inline `<style>` injection.

### Fixed

- Fixed `open_editor` session leak where manually closing the browser window
  left the account stuck as "already open" until bridge restart.
- Updated `ensureBridgeScript` to compare file contents and overwrite outdated
  `csdn_bridge.py` copies on plugin upgrade.
- Replaced `window.prompt` and `window.confirm` dialogs with native Obsidian
  `Modal` dialogs.
- Improved draft tab detection to match by tab label before falling back to
  index, and made draft listing/deletion run headless by default.
- Fixed cross-platform profile directory resolution and removed hardcoded local
  paths from error messages.
- Unified ribbon menu labels to Chinese and relaxed `requirements.txt` to
  `playwright>=1.50.0`.

## [0.6.1] - 2026-08-31

### Fixed

- Removed the word "Obsidian" from the plugin description per community
  directory review guidelines.

## [0.6.0] - 2026-08-31

### Added

- Bridge script now ships inside the plugin folder: `main.js` writes the
  embedded copy next to itself on first run and spawns it via `manifest.dir`
  instead of a vault-relative `tools/` path.
- English README with privacy and data disclosures (network use, CSDN account,
  files outside the vault).
- MIT license and `versions.json`.

### Changed

- Personal interpreter paths removed from defaults; the default Python command
  is now `python`.
