# Contributing

Thanks for your interest in improving CSDN Draft Publisher.

## Project layout

- `main.js` — plugin source. Plain JavaScript, no build step and no bundler.
  It embeds a base64 copy of the bridge script
  (`EMBEDDED_BRIDGE_SCRIPT_B64`) and writes it next to itself on first run.
- `csdn_bridge.py` — the Python bridge. This file is the **source of truth**
  for the embedded copy.
- `manifest.json` — plugin metadata and the **single version source**.
- `versions.json` — maps each plugin version to the minimum Obsidian version.

## Development setup

1. Copy or symlink this folder to `<vault>/.obsidian/plugins/csdn-draft-publisher/`.
2. Reload Obsidian (Ctrl+P → "Reload app without saving").
3. For the bridge: Python 3.11+ with
   `pip install playwright && python -m playwright install chromium`.

## Local checks (must pass before every PR, same as CI)

```bash
node --check main.js
python -m py_compile csdn_bridge.py
```

If you changed `csdn_bridge.py`, regenerate the embedded constant so the
round-trip check stays green:

```bash
node -e "const fs=require('fs');const b64=fs.readFileSync('csdn_bridge.py').toString('base64');let m=fs.readFileSync('main.js','utf8');m=m.replace(/EMBEDDED_BRIDGE_SCRIPT_B64 =\s*\"[^\"]+\"/,'EMBEDDED_BRIDGE_SCRIPT_B64 =\n  \"'+b64+'\"');fs.writeFileSync('main.js',m);"
```

## Branch, commit and PR rules

- `main` stays releasable at all times; use short-lived branches:
  `feat/<name>`, `fix/<name>`, `docs/<name>`, `chore/<name>`.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:` / `fix:` / `docs:` / `chore:` / `release:`.
- One PR does one thing. Squash-merge is the standard merge strategy.
- User-visible changes must update `README.md` and `CHANGELOG.md`
  (`Unreleased` section).
- Never commit credentials, local paths, runtime data, or
  `%LOCALAPPDATA%\CSDN-Draft-Publisher` profile content.

## Releases

Releases are executed by the maintainer following
[RELEASE-CHECKLIST.md](./RELEASE-CHECKLIST.md). Note one deliberate deviation
from common Git conventions: **release tags carry no `v` prefix** (e.g. `0.6.1`)
because the Obsidian community directory resolves releases by matching the tag
exactly against the version string in `manifest.json`. CI enforces this
equality.
