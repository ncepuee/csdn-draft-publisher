# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).
Release tags use the exact manifest version (`0.6.1`, not `v0.6.1`) as required
by the Obsidian community directory.

## [Unreleased]

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
