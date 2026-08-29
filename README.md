# Obsidian → CSDN 草稿同步助手

这是一个安装在当前 Vault 中的本地 Obsidian 插件，配合 Python + Playwright 桥接服务，把当前 Markdown 笔记填入 CSDN Markdown 编辑器并保存为草稿。

## 已实现

- 命令面板：`同步当前笔记到 CSDN 草稿`
- 右侧 Ribbon 图标一键同步
- 从 YAML frontmatter 读取 `title`、`description`/`summary`、`tags`、`cover`/`image`
- 复用本地 Playwright 浏览器配置保存登录态，不保存 CSDN 用户名和密码
- 只寻找“保存草稿/保存”按钮或自动保存提示
- 自动化逻辑明确排除“发布”按钮
- 检测本地图片引用并提醒；当前版本不自动上传 CSDN 图片
- 插件设置页支持桥接服务开关：开启时自动启动本地 Python 服务，关闭时只停止插件启动的服务
- 支持多个 CSDN 账号，每个账号使用独立的 Playwright 浏览器 profile
- 草稿箱管理：读取草稿列表、标题搜索、分页、打开编辑和二次确认删除
- 侧栏只保留一个 CSDN 图标，点击后选择同步笔记或打开草稿箱管理

## 首次使用

推荐使用独立 Conda 环境，不要把 Playwright 装进 Anaconda `base`：

```powershell
conda env create -f G:\Obnotes\tools\csdn-draft-publisher\environment.yml
conda run -n csdn-publisher python -m playwright install chromium
```

当前环境已经安装在 `C:\Users\hzb\.conda\envs\csdn-publisher`。重启 Obsidian后，在插件设置中确认 Python 解释器指向：

```text
C:\Users\hzb\.conda\envs\csdn-publisher\python.exe
```

然后打开“启用桥接服务”。打开一篇 Markdown 笔记，执行命令面板命令即可。首次运行会打开浏览器，手动完成 CSDN 登录；后续同步复用本地浏览器配置。

## 草稿箱管理

在命令面板执行 `打开 CSDN 草稿箱管理`，或点击插件的 CSDN 图标即可打开管理面板。面板会读取当前选中账号的 CSDN 草稿箱，支持标题搜索、刷新、分页、打开编辑和删除。删除操作会在插件中二次确认，并通过 CSDN 内容管理页面执行；不会直接保存账号密码或复制登录 Cookie。

## 多账号切换

在插件设置页的“当前 CSDN 账号”区域点击“新增账号”，输入账号名称，再点击该账号的“登录”。每个账号都使用独立的浏览器配置目录：

```text
%LOCALAPPDATA%\\CSDN-Draft-Publisher\\playwright-profile       # 默认账号，兼容旧登录态
%LOCALAPPDATA%\\CSDN-Draft-Publisher\\profiles\\account-*     # 新增账号
```

登录完成后，在“当前 CSDN 账号”下拉框中切换账号。插件不会保存 CSDN 用户名或密码，只保存 Chromium 的本地登录态。点击“清除登录态”会删除对应账号的 Cookie 和本地会话；不会影响其他账号。

插件会自动运行当前 Vault 下的 `tools/csdn-draft-publisher/csdn_bridge.py`，默认监听 `127.0.0.1:8765`。如果 8765 端口已经有你手动启动的桥接服务，插件只会复用它，不会在关闭开关时误停止外部进程。

## 推荐 frontmatter

```yaml
---
title: 我的技术文章
description: 一句话摘要
tags:
  - Python
  - 自动化
cover: _attachments/cover.png
---
```

## 调研结论

- [ddean2009/blog-auto-publishing-tools](https://github.com/ddean2009/blog-auto-publishing-tools)：成熟的多平台 Selenium 自动化工具，包含 CSDN 发布器；它依赖浏览器登录态和页面选择器，适合作为交互参考。
- [Obsidian 社区插件目录](https://github.com/obsidianmd/obsidian-releases)：截至本次调研，没有发现专门把当前 Obsidian 笔记一键写入 CSDN 草稿的成熟社区插件。
- [prepare-csdn-draft 介绍](https://aicoding.csdn.net/6a5e478b10ee7a33f2904eee.html)：近期方案更偏向生成本地 CSDN 发布包，不登录、不控制浏览器，因此不能替代本助手的草稿同步。

## 已知限制

CSDN 编辑器是动态页面，DOM、按钮文案和风控策略可能变化。同步成功后仍建议在浏览器中检查标题、正文、图片、标签和摘要。若桥接服务报告未确认保存状态，页面通常已经填入内容，但需要手动点击 CSDN 的保存入口。

Playwright 包和浏览器版本需要匹配；升级 Playwright 后应在同一个 Conda 环境中重新执行 `python -m playwright install chromium`。浏览器二进制使用 Windows 默认缓存目录 `%USERPROFILE%\AppData\Local\ms-playwright`，登录态则单独保存在 `%LOCALAPPDATA%\CSDN-Draft-Publisher\playwright-profile`。
