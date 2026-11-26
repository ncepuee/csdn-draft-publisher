<h1 align="center">CSDN Draft Publisher</h1>

<p align="center"><a href="README.md">English</a> | 简体中文</p>

<p align="center">一款将当前 <a href="https://obsidian.md">Obsidian</a> Markdown 笔记同步到 <a href="https://www.csdn.net">CSDN</a> 博客草稿箱，并支持在库内直接管理、回写草稿的插件。</p>

<p align="center">
  <img alt="Antigravity Code Support" src="https://img.shields.io/badge/Antigravity-Code_Support-4285F4?logo=google&amp;logoColor=white">
  <a href="https://gemini.google.com/"><img alt="Gemini 4 Carbon Agent" src="https://img.shields.io/badge/Gemini_4_Carbon-Agent_used%400.9.0-4285F4?logo=googlegemini&amp;logoColor=white"></a>
  <a href="https://github.com/ncepuee/csdn-draft-publisher"><img alt="GitHub stars" src="https://img.shields.io/github/stars/ncepuee/csdn-draft-publisher?logo=github&amp;cacheSeconds=86400"></a>
</p>

<p align="center">
  <a href="https://github.com/ncepuee/csdn-draft-publisher/releases"><img alt="Release" src="https://img.shields.io/github/v/release/ncepuee/csdn-draft-publisher"></a>
  <a href="https://github.com/ncepuee/csdn-draft-publisher/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/ncepuee/csdn-draft-publisher/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/ncepuee/csdn-draft-publisher/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/ncepuee/csdn-draft-publisher"></a>
</p>

## 核心功能

> **完整使用文档见 [Wiki](https://github.com/ncepuee/csdn-draft-publisher/wiki)**（含 [中文快速上手指南](https://github.com/ncepuee/csdn-draft-publisher/wiki/%E4%B8%AD%E6%96%87%E4%BD%BF%E7%94%A8%E6%8C%87%E5%8D%97)）。

- **中英文双语界面**：支持跟随 Obsidian 语言、简体中文、English 三档切换，无需重启立即生效
- **内嵌扫码登录**：直接在 Obsidian 弹窗中展示 **微信扫码 / CSDN APP 扫码** 二维码，免弹浏览器窗口（同时保留浏览器窗口登录兜底）
- **一键草稿同步与回写更新**：读取 YAML frontmatter 中的 `title`、`description` / `summary`、`tags`、`cover` / `image`，首次同步后自动将 `csdn_article_id` 写回笔记属性，后续同步直接更新同一篇草稿
- **Obsidian 专属语法预处理**：同步前可选自动转换 `[[双链|别名]]`、`> [!callout]` 标题并剥离 `%%注释%%`（自动跳过代码块）
- **库内草稿箱面板**：无头静默浏览当前账号草稿、按标题搜索、分页、导入本地编辑回写、确认后删除草稿
- **多账号隔离**：支持新增、重命名、删除、静默验证登录态与清除会话，每个账号拥有独立浏览器配置目录
- **安全只存草稿**：自动化脚本严禁点击任何包含“发布”字样的按钮，仅执行保存草稿

## 工作原理

插件内置了 Python 桥接脚本 `csdn_bridge.py`（内嵌在 `main.js` 中，启用或升级时自动释放/更新到插件目录）。插件通过本地 HTTP（默认 `http://127.0.0.1:8765`）调用桥接服务，由 [Playwright](https://playwright.dev/python/docs/intro) 驱动本机 Chrome / Edge 或 Chromium 内核完成扫码登录、草稿读取与保存。

## 隐私与安全说明

- **零遥测**：不收集、不上报任何使用数据。
- **不存储密码**：从不索取或保存 CSDN 账号密码；扫码或浏览器登录后的会话仅保存在本机 `%LOCALAPPDATA%\CSDN-Draft-Publisher\`（macOS/Linux 对应用户数据目录）下的独立浏览器配置中。
- **网络边界**：桥接服务仅监听 `127.0.0.1`，除向 `csdn.net` 同步草稿外不向任何第三方发送笔记内容。

## 快速安装与配置

1. 下载 Release 中的 `main.js`、`manifest.json`、`styles.css` 放入 `<你的库>/.obsidian/plugins/csdn-draft-publisher/`，在第三方插件中启用。
2. 准备 Python 3.11+ 环境并安装 `playwright`（若本机已安装 Chrome 或 Microsoft Edge，甚至无需额外下载浏览器内核）：

   ```bash
   pip install "playwright>=1.50.0"
   ```

3. 打开插件设置，将 **Python 解释器** 指向安装了 `playwright` 的 Python 路径，开启 **启用桥接服务**。
4. 点击账号旁的 **扫码登录** 完成授权，随后即可通过命令面板或左侧图标同步笔记与管理草稿箱。

## 推荐 Frontmatter

```yaml
---
title: 文章标题
description: 一句话文章摘要
tags:
  - Python
  - Obsidian
cover: https://example.com/cover.png
---
```

## 参与贡献

本地检查命令、分支与提交规范以及发布清单请参见 [CONTRIBUTING.md](./CONTRIBUTING.md) 与 [RELEASE-CHECKLIST.md](./RELEASE-CHECKLIST.md)。安全问题请按 [SECURITY.md](./SECURITY.md) 私密上报。

## 许可证

[MIT](./LICENSE)
