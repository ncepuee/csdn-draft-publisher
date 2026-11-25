# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).
Release tags use the exact manifest version (`0.6.1`, not `v0.6.1`) as required
by the Obsidian community directory.

## [Unreleased]

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
