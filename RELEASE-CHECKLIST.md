# RELEASE-CHECKLIST.md

> 发布 vX.Y.Z 前逐项打勾，不许跳步。本仓库的发布 SOP 落点：
> tag **不带 `v` 前缀**且必须与 `manifest.json` 的 `version` 完全一致
> （Obsidian 社区目录按 tag 精确匹配解析下载，这是对通用 SOP 的唯一偏差，
> 一致性由 CI 兜底校验）。
>
> 占位符代入：`<VERSION_FILE>` = `manifest.json`（version 字段）；
> `<SELF_CHECK_CMD>` = CONTRIBUTING.md「Local checks」三连；
> `<PUBLISH_CMD>` = 创建 GitHub Release 并附 `main.js` + `manifest.json`。

## 发布前

- [ ] `git fetch origin --prune && git status --short --branch` — main 与远程同步、工作区干净
- [ ] 发版判定完成：本次为何发版、为何升 patch/minor/major（记录在 PR 或 Release Notes）
- [ ] `CHANGELOG.md` 的 `Unreleased` 段已整理为本版本段落
- [ ] `manifest.json` 的 `version` 改为 `X.Y.Z`（单一版本源，只改这一处）
- [ ] `versions.json` 已加入 `"X.Y.Z": "<minAppVersion>"`
- [ ] 本地自检通过（与 CI 等价）：
  - [ ] `node --check main.js`
  - [ ] `python -m py_compile csdn_bridge.py`
  - [ ] 内嵌桥接 round-trip 校验（CONTRIBUTING.md「Local checks」）
  - [ ] manifest 校验：描述 ≤250 字符、不含 "Obsidian" 一词、id 合规
- [ ] 敏感信息扫描：不含凭据、`C:\Users\...` 等本机私有路径、运行时数据

## 发布

- [ ] 提交 `release: 0.X.Y` 并 push，**等 main 的 CI（Verify）全绿**
- [ ] 打 tag `X.Y.Z`（不带 v）并 push，等 tag 触发的 CI 全绿（含 tag 一致性校验）
- [ ] CI 绿后创建 GitHub Release：
  - [ ] 标题：`CSDN Draft Publisher vX.Y.Z`
  - [ ] 正文：复制 CHANGELOG 对应段落 + Verification 摘要
  - [ ] 资产：`main.js`、`manifest.json`（Obsidian 目录读取这两个）
  - [ ] 校验和：`SHA256SUMS-X.Y.Z.txt`（`sha256sum main.js manifest.json > SHA256SUMS-X.Y.Z.txt`）
- [ ] Release 一经发布即不可变；发现问题只能发新版本，不覆盖不重发同号

## 发布后

- [ ] `git ls-remote --tags origin` 能看到新 tag
- [ ] [community.obsidian.md](https://community.obsidian.md) 条目页自动出现新版本，
      自动检查全绿（若 MANIFEST/RELEASES 报错按提示修复后发新版本）
- [ ] 干净环境（或 Vault 副本）更新插件并验证：命令面板、Ribbon、桥接启动、草稿同步
- [ ] 用 SHA256SUMS 复核下载到的 `main.js`
