# Security Policy

- Found a security vulnerability? **Do not open a public issue.**
- Report it privately via GitHub:
  **Security → Report a vulnerability**
  (<https://github.com/ncepuee/csdn-draft-publisher/security/advisories/new>).
- You will get an acknowledgement within 48 hours. Fixes land in the next
  patch release, and reporters are credited in the release notes unless they
  prefer to stay anonymous.

## Scope notes for this plugin

- The plugin spawns a local Python process and drives a Playwright browser
  against csdn.net. Reports involving credential leakage, prompt injection
  through note content reaching shell commands, or bridge network exposure
  beyond `127.0.0.1` are especially welcome.
- The plugin never stores CSDN usernames or passwords; login state lives in a
  local Chromium profile under `%LOCALAPPDATA%\CSDN-Draft-Publisher\`.
