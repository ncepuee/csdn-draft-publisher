const obsidian = require("obsidian");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const {
  addIcon,
  Plugin,
  Notice,
  PluginSettingTab,
  Setting,
  requestUrl,
  ItemView,
  Menu,
} = obsidian;

const CSDN_ICON_SVG = `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M4.693 13.638c-.497.568-1.363.63-1.712.63-.648 0-1.144-.164-1.474-.488-.313-.307-.478-.76-.489-1.346-.025-1.358.744-2.762 2.074-2.762.635 0 1.124.455 1.311.644a.337.337 0 0 0 .282.099.38.38 0 0 0 .241-.159c.068-.087.135-.237.138-.401s-.057-.344-.243-.49a2.642 2.642 0 0 0-1.668-.591c-.819 0-1.627.376-2.218 1.033-.621.691-.953 1.63-.935 2.646.015.815.282 1.5.773 1.982.528.518 1.3.791 2.235.791 1.097 0 1.776-.325 2.154-.597a.584.584 0 0 0 .24-.456.702.702 0 0 0-.208-.497c-.23-.248-.448-.101-.503-.037ZM9.663 11.488a7.471 7.471 0 0 0-.698-.248c-.157-.048-.309-.091-.45-.131-.922-.26-1.027-.5-1.017-.68.022-.363.515-.853 1.352-.792.607.045 1.015.509 1.205.781.149.214.371.135.434.095a.602.602 0 0 0 .309-.514.626.626 0 0 0-.209-.488 2.654 2.654 0 0 0-3.347-.273c-.456.323-.744.772-.77 1.202-.064 1.061 1.015 1.366 1.803 1.588.214.061.429.127.667.202 1.14.357 1.173.717 1.092 1.267-.082.556-.696.834-1.685.761-1.029-.076-1.464-.61-1.612-.901-.05-.098-.205-.248-.413-.156-.514.229-.473.731-.26.993.339.416 1.15 1.035 2.667 1.035 1.734 0 2.255-.875 2.378-1.64.092-.572-.022-1.028-.348-1.396-.236-.267-.592-.495-1.101-.706ZM16.44 9.323c-.598-.431-1.393-.61-2.36-.532-.712.058-1.274.243-1.335.263l-.006.002a.437.437 0 0 0-.297.379l-.47 5.201a.337.337 0 0 0 .247.35l.072.02.066.018.086.021a7.914 7.914 0 0 0 1.64.183c.972 0 1.765-.23 2.36-.684.764-.583 1.141-1.5 1.118-2.725-.021-1.135-.398-1.974-1.121-2.495Zm-.662 4.461c-.836.639-2.09.562-2.677.481a.128.128 0 0 1-.109-.137l.397-4.248a.113.113 0 0 1 .086-.1c.999-.241 1.777-.168 2.312.218.189.137.348.331.471.568.176.339.277.765.286 1.234.017.916-.24 1.583-.765 1.984ZM23.967 10.41a1.92 1.92 0 0 0-.432-.919c-.399-.465-1.029-.689-1.848-.689-.734 0-1.372.228-1.947.799.007-.086.019-.159.018-.223s-.017-.116-.066-.163c-.048-.045-.077-.067-.127-.077-.05-.01-.122-.008-.256-.006a.587.587 0 0 0-.589.54s-.325 3.874-.428 5.165a.308.308 0 0 0 .073.228.36.36 0 0 0 .26.131h.387a.224.224 0 0 0 .226-.205l.273-2.929.014-.147a1.902 1.902 0 0 1 .082-.412c.014-.045.03-.092.047-.14.245-.694.803-1.72 1.971-1.694.84.018 1.449.455 1.385 1.114-.101 1.034-.266 3.1-.358 4.14-.019.209.182.273.252.273h.304a.442.442 0 0 0 .444-.404s.185-2.127.294-3.352l.048-.532a1.959 1.959 0 0 0-.026-.5Z"/></svg>`;

const CSDN_C_ICON_SVG = `<svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg"><path d="M512 0c282.784 0 512 229.216 512 512s-229.216 512-512 512S0 794.784 0 512 229.216 0 512 0z m189.952 752l11.2-108.224c-31.904 9.536-100.928 16.128-147.712 16.128-134.464 0-205.728-47.296-195.328-146.304 11.584-110.688 113.152-145.696 232.64-145.696 54.784 0 122.432 8.8 151.296 18.336L768 272.704C724.544 262.24 678.272 256 599.584 256c-203.2 0-388.704 94.88-406.4 263.488C178.336 660.96 303.584 768 535.616 768c80.672 0 138.464-6.432 166.336-16z" fill="#CE000D"/></svg>`;

const BRIDGE_API_VERSION = "0.5.0";
const DRAFT_VIEW_TYPE = "csdn-draft-box";
const DRAFT_VIEW_ICON = "csdn-brand";

const DEFAULT_SETTINGS = {
  bridgeUrl: "http://127.0.0.1:8765",
  bridgeEnabled: false,
  pythonCommand: "C:\\Users\\hzb\\.conda\\envs\\csdn-publisher\\python.exe",
  accounts: [{ id: "default", name: "默认账号" }],
  activeAccountId: "default",
  openBrowser: true,
  autoSaveWaitSeconds: 5,
};

function asString(value) {
  if (value === undefined || value === null) return "";
  return String(value).trim();
}

function parseFrontmatter(raw) {
  const match = raw.match(/^---\s*\r?\n([\s\S]*?)\r?\n---\s*(?:\r?\n|$)/);
  if (!match) return { data: {}, body: raw };

  const data = {};
  const lines = match[1].split(/\r?\n/);
  let activeListKey = null;
  for (const line of lines) {
    const listItem = line.match(/^\s*-\s*(.+?)\s*$/);
    if (listItem && activeListKey) {
      if (!Array.isArray(data[activeListKey])) data[activeListKey] = [];
      data[activeListKey].push(stripYamlScalar(listItem[1]));
      continue;
    }

    const pair = line.match(/^\s*([\w-]+)\s*:\s*(.*?)\s*$/);
    if (!pair) continue;
    const key = pair[1];
    const value = pair[2];
    if (!value) {
      data[key] = [];
      activeListKey = key;
      continue;
    }
    activeListKey = null;
    if (value.startsWith("[") && value.endsWith("]")) {
      data[key] = value
        .slice(1, -1)
        .split(",")
        .map((item) => stripYamlScalar(item))
        .filter(Boolean);
    } else {
      data[key] = stripYamlScalar(value);
    }
  }

  return { data, body: raw.slice(match[0].length) };
}

function stripYamlScalar(value) {
  const text = asString(value);
  if ((text.startsWith("\"") && text.endsWith("\"")) ||
      (text.startsWith("'") && text.endsWith("'"))) {
    return text.slice(1, -1);
  }
  return text;
}

function normalizeList(value) {
  if (Array.isArray(value)) return value.map(asString).filter(Boolean);
  if (!value) return [];
  return String(value)
    .split(/[，,\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function firstHeading(body) {
  const match = body.match(/^\s*#\s+(.+?)\s*$/m);
  return match ? match[1].trim() : "";
}

function removeDuplicateTitle(body, title) {
  const lines = body.split(/\r?\n/);
  const firstContentIndex = lines.findIndex((line) => line.trim() !== "");
  if (firstContentIndex < 0) return body.trim();
  const first = lines[firstContentIndex].match(/^\s*#\s+(.+?)\s*$/);
  if (first && first[1].trim() === title.trim()) {
    lines.splice(firstContentIndex, 1);
  }
  return lines.join("\n").trim();
}

function findLocalImages(body) {
  const paths = [];
  const wikiPattern = /!\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]/g;
  const markdownPattern = /!\[[^\]]*\]\(([^)]+)\)/g;
  for (const match of body.matchAll(wikiPattern)) paths.push(match[1].trim());
  for (const match of body.matchAll(markdownPattern)) {
    const target = match[1].trim().replace(/^<|>$/g, "");
    if (!/^(https?:|data:|file:)/i.test(target)) paths.push(target);
  }
  return [...new Set(paths)];
}

function yamlString(value) {
  return JSON.stringify(asString(value));
}

function safeDraftFileName(title, articleId) {
  const cleaned = asString(title)
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/[. ]+$/g, "")
    .slice(0, 80);
  return `${cleaned || "未命名草稿"}-${articleId}.md`;
}

const CSDN_DRAFT_CSS = `
.csdn-draft-box-view {
  --csdn-red: #ce000d;
  --csdn-ink: var(--text-normal);
  --csdn-muted: var(--text-muted);
  --csdn-card: color-mix(in srgb, var(--background-primary) 88%, var(--background-secondary));
  --csdn-card-hover: color-mix(in srgb, var(--background-primary) 96%, var(--background-modifier-hover));
  padding: 28px 24px 36px;
  overflow: auto;
  background:
    radial-gradient(circle at 85% 0%, color-mix(in srgb, var(--csdn-red) 7%, transparent), transparent 30%),
    var(--background-primary);
}
.csdn-draft-box-view .csdn-draft-box-shell { max-width: 980px; margin: 0 auto; }
.csdn-draft-box-view .csdn-draft-box-hero { display: flex; justify-content: space-between; align-items: flex-end; gap: 20px; margin-bottom: 24px; }
.csdn-draft-box-view .csdn-draft-box-eyebrow { color: var(--csdn-red); font-size: 11px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
.csdn-draft-box-view h2 { margin: 5px 0 6px; font-size: 30px; line-height: 1.08; letter-spacing: -.035em; }
.csdn-draft-box-view .csdn-draft-box-subtitle { max-width: 620px; margin: 0; color: var(--csdn-muted); font-size: 13px; line-height: 1.55; }
.csdn-draft-box-view .csdn-draft-box-account { color: var(--csdn-ink); font-size: 12px; font-weight: 600; white-space: nowrap; }
.csdn-draft-box-view .csdn-draft-box-summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 18px; }
.csdn-draft-box-view .csdn-draft-box-stat { padding: 14px 16px; border: 1px solid var(--background-modifier-border); border-radius: 16px; background: color-mix(in srgb, var(--background-secondary) 62%, transparent); }
.csdn-draft-box-view .csdn-draft-box-stat-label { color: var(--csdn-muted); font-size: 11px; }
.csdn-draft-box-view .csdn-draft-box-stat-value { margin-top: 4px; color: var(--csdn-ink); font-size: 20px; font-weight: 700; letter-spacing: -.02em; }
.csdn-draft-box-view .csdn-draft-box-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
.csdn-draft-box-view .csdn-draft-box-search { flex: 1; min-width: 120px; height: 36px; padding: 0 13px; border: 1px solid var(--background-modifier-border); border-radius: 10px; background: var(--background-secondary); color: var(--text-normal); }
.csdn-draft-box-view .csdn-draft-box-toolbar button, .csdn-draft-box-view .csdn-draft-box-actions button, .csdn-draft-box-view .csdn-draft-box-pager button { border-radius: 9px; }
.csdn-draft-box-view .csdn-draft-box-toolbar button { height: 36px; padding: 0 13px; }
.csdn-draft-box-view .csdn-draft-box-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(265px, 1fr)); gap: 14px; }
.csdn-draft-box-view .csdn-draft-box-card { position: relative; display: flex; min-height: 194px; flex-direction: column; padding: 18px; border: 1px solid color-mix(in srgb, var(--background-modifier-border) 78%, transparent); border-radius: 18px; background: var(--csdn-card); box-shadow: 0 8px 28px color-mix(in srgb, var(--background-primary) 65%, transparent); transition: transform 160ms ease, background 160ms ease, box-shadow 160ms ease; }
.csdn-draft-box-view .csdn-draft-box-card:hover { transform: translateY(-2px); background: var(--csdn-card-hover); box-shadow: 0 12px 34px color-mix(in srgb, var(--background-primary) 48%, transparent); }
.csdn-draft-box-view .csdn-draft-box-card:active { transform: scale(.99); }
.csdn-draft-box-view .csdn-draft-box-card-top { display: flex; justify-content: space-between; align-items: center; color: var(--csdn-muted); font-size: 11px; }
.csdn-draft-box-view .csdn-draft-box-badge { color: var(--csdn-red); font-weight: 700; }
.csdn-draft-box-view .csdn-draft-box-card h3 { display: -webkit-box; overflow: hidden; margin: 18px 0 8px; color: var(--csdn-ink); font-size: 16px; line-height: 1.38; letter-spacing: -.015em; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.csdn-draft-box-view .csdn-draft-box-card-meta { margin-top: auto; color: var(--csdn-muted); font-size: 11px; }
.csdn-draft-box-view .csdn-draft-box-actions { display: flex; gap: 8px; margin-top: 15px; }
.csdn-draft-box-view .csdn-draft-box-actions button:first-child { flex: 1; border-color: color-mix(in srgb, var(--csdn-red) 35%, var(--background-modifier-border)); color: var(--csdn-red); font-weight: 650; }
.csdn-draft-box-view .csdn-draft-box-actions button:last-child { color: var(--text-muted); }
.csdn-draft-box-view .csdn-draft-box-state { grid-column: 1 / -1; padding: 42px 20px; border: 1px dashed var(--background-modifier-border); border-radius: 18px; color: var(--csdn-muted); text-align: center; }
.csdn-draft-box-view .csdn-draft-box-skeleton { height: 194px; border-radius: 18px; background: linear-gradient(100deg, var(--background-secondary) 35%, var(--background-modifier-hover) 50%, var(--background-secondary) 65%); background-size: 300% 100%; animation: csdn-draft-shimmer 1.2s ease-in-out infinite; }
.csdn-draft-box-view .csdn-draft-box-pager { display: flex; justify-content: center; align-items: center; gap: 12px; margin-top: 22px; color: var(--csdn-muted); font-size: 12px; }
@keyframes csdn-draft-shimmer { from { background-position: 100% 0; } to { background-position: -100% 0; } }
@media (max-width: 620px) { .csdn-draft-box-view { padding: 20px 14px 28px; } .csdn-draft-box-view .csdn-draft-box-hero { display: block; } .csdn-draft-box-view .csdn-draft-box-account { display: block; margin-top: 10px; } .csdn-draft-box-view .csdn-draft-box-summary { grid-template-columns: 1fr 1fr; } }
@media (prefers-reduced-motion: reduce) { .csdn-draft-box-view .csdn-draft-box-card, .csdn-draft-box-view .csdn-draft-box-skeleton { animation: none; transition: none; } .csdn-draft-box-view .csdn-draft-box-card:hover { transform: none; } }
`;

function normalizeAccounts(settings) {
  const accounts = Array.isArray(settings.accounts)
    ? settings.accounts
      .filter((account) => account && account.id && account.name)
      .map((account) => ({ id: String(account.id), name: String(account.name) }))
    : [];
  if (!accounts.some((account) => account.id === "default")) {
    accounts.unshift({ id: "default", name: "默认账号" });
  }
  const activeAccountId = accounts.some((account) => account.id === settings.activeAccountId)
    ? settings.activeAccountId
    : accounts[0].id;
  return { accounts, activeAccountId };
}

class CsdnDraftPublisherSettingTab extends PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display() {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("h2", { text: "CSDN 草稿同步" });

    containerEl.createEl("p", {
      text: "插件只调用本机桥接服务；CSDN 登录态保存在 Playwright 浏览器配置中，不保存账号密码。",
      cls: "setting-item-description",
    });

    const accountState = normalizeAccounts(this.plugin.settings);
    this.plugin.settings.accounts = accountState.accounts;
    this.plugin.settings.activeAccountId = accountState.activeAccountId;

    new Setting(containerEl)
      .setName("当前 CSDN 账号")
      .setDesc("每个账号使用独立浏览器登录态；切换后新同步任务使用所选账号。")
      .addDropdown((dropdown) => {
        for (const account of accountState.accounts) {
          dropdown.addOption(account.id, account.name);
        }
        dropdown
          .setValue(accountState.activeAccountId)
          .onChange(async (value) => {
            this.plugin.settings.activeAccountId = value;
            await this.plugin.saveSettings();
            const account = this.plugin.getAccount(value);
            new Notice(`已切换到 CSDN 账号：${account?.name || value}`, 5000);
          });
      });

    new Setting(containerEl)
      .setName("账号管理")
      .setDesc("新增账号后点击“登录”，在对应的浏览器窗口中完成 CSDN 登录。")
      .addButton((button) => button
        .setButtonText("新增账号")
        .onClick(async () => {
          const name = window.prompt("请输入账号名称，例如：工作号、个人号");
          if (!name || !name.trim()) return;
          const account = await this.plugin.addAccount(name.trim());
          await this.plugin.saveSettings();
          this.display();
          new Notice(`账号“${account.name}”已添加，请点击该账号旁的“登录”。`, 8000);
        }));

    for (const account of accountState.accounts) {
      const isActive = account.id === accountState.activeAccountId;
      new Setting(containerEl)
        .setName(`${account.name}${isActive ? "（当前）" : ""}`)
        .setDesc(`独立登录态：${account.id === "default" ? "兼容原有登录态" : "独立浏览器配置"}`)
        .addButton((button) => button
          .setButtonText("登录")
          .onClick(async () => {
            button.setDisabled(true);
            try {
              await this.plugin.loginAccount(account.id);
              new Notice(`已打开“${account.name}”的登录窗口，请完成 CSDN 登录。`, 8000);
            } catch (error) {
              new Notice(`无法打开登录窗口：${error.message}`, 10000);
            } finally {
              button.setDisabled(false);
            }
          }))
        .addButton((button) => button
          .setButtonText("检查")
          .onClick(async () => {
            button.setDisabled(true);
            try {
              const result = await this.plugin.sessionAccount(account.id);
              const status = result.status === "logged_in" ? "已检测到登录完成" : result.message;
              new Notice(`${account.name}：${status}`, 8000);
            } catch (error) {
              new Notice(`检查账号失败：${error.message}`, 10000);
            } finally {
              button.setDisabled(false);
            }
          }))
        .addButton((button) => button
          .setWarning()
          .setButtonText("清除登录态")
          .onClick(async () => {
            if (!window.confirm(`确定清除“${account.name}”的登录态吗？`)) return;
            button.setDisabled(true);
            try {
              await this.plugin.logoutAccount(account.id);
              new Notice(`已清除“${account.name}”的登录态。`, 5000);
            } catch (error) {
              new Notice(`清除登录态失败：${error.message}`, 10000);
            } finally {
              button.setDisabled(false);
            }
          }));
    }

    new Setting(containerEl)
      .setName("启用桥接服务")
      .setDesc("开启后由插件自动启动本地 Python 桥接服务；关闭时只停止插件自己启动的进程。")
      .addToggle((toggle) => toggle
        .setValue(this.plugin.settings.bridgeEnabled)
        .onChange(async (value) => {
          toggle.setDisabled(true);
          this.plugin.settings.bridgeEnabled = value;
          await this.plugin.saveSettings();
          try {
            if (value) {
              const result = await this.plugin.startBridge();
              const prefix = result.external
                ? "检测到桥接服务已经在运行"
                : "桥接服务已启动";
              const suffix = result.playwright === false
                ? "，但 Playwright 尚未安装"
                : "";
              new Notice(`${prefix}${suffix}。`, 8000);
            } else {
              this.plugin.stopManagedBridge();
              new Notice("桥接服务开关已关闭。", 5000);
            }
          } catch (error) {
            this.plugin.settings.bridgeEnabled = false;
            await this.plugin.saveSettings();
            toggle.setValue(false);
            new Notice(`桥接服务启动失败：${error.message}`, 10000);
          } finally {
            toggle.setDisabled(false);
          }
        }));

    new Setting(containerEl)
      .setName("桥接服务地址")
      .setDesc("默认 http://127.0.0.1:8765")
      .addText((text) => text
        .setPlaceholder(DEFAULT_SETTINGS.bridgeUrl)
        .setValue(this.plugin.settings.bridgeUrl)
        .onChange(async (value) => {
          this.plugin.settings.bridgeUrl = value.trim().replace(/\/$/, "");
          await this.plugin.saveSettings();
        }));

    new Setting(containerEl)
      .setName("Python 解释器")
      .setDesc("桥接服务使用的 Python 路径。推荐使用 csdn-publisher Conda 环境。")
      .addText((text) => text
        .setPlaceholder(DEFAULT_SETTINGS.pythonCommand)
        .setValue(this.plugin.settings.pythonCommand)
        .onChange(async (value) => {
          this.plugin.settings.pythonCommand = value.trim();
          await this.plugin.saveSettings();
        }));

    new Setting(containerEl)
      .setName("同步时打开浏览器")
      .setDesc("建议开启，首次使用时可扫码登录或处理验证码。")
      .addToggle((toggle) => toggle
        .setValue(this.plugin.settings.openBrowser)
        .onChange(async (value) => {
          this.plugin.settings.openBrowser = value;
          await this.plugin.saveSettings();
        }));

    new Setting(containerEl)
      .setName("自动保存等待时间")
      .setDesc("填入正文后等待 CSDN 自动保存的秒数。")
      .addSlider((slider) => slider
        .setLimits(2, 20, 1)
        .setValue(this.plugin.settings.autoSaveWaitSeconds)
        .setDynamicTooltip()
        .onChange(async (value) => {
          this.plugin.settings.autoSaveWaitSeconds = value;
          await this.plugin.saveSettings();
        }));

    new Setting(containerEl)
      .setName("检查桥接服务")
      .setDesc("确认本机 Python 服务是否已经启动。")
      .addButton((button) => button
        .setButtonText("检查")
        .onClick(async () => {
          button.setDisabled(true);
          try {
            const result = await this.plugin.healthCheck();
            const version = result.bridge_api_version || "旧版";
            const accountSupport = result.account_profiles ? "多账号已启用" : "不支持多账号";
            new Notice(`CSDN 桥接服务正常（API ${version}，Playwright: ${result.playwright ? "已安装" : "未安装"}，${accountSupport}）`);
          } catch (error) {
            const hint = this.plugin.settings.bridgeEnabled
              ? "请检查 Python/Playwright 依赖。"
              : "请先打开“启用桥接服务”开关。";
            new Notice(`桥接服务不可用：${error.message}\n${hint}`, 10000);
          } finally {
            button.setDisabled(false);
          }
        }));
  }
}

class CsdnDraftPublisher extends Plugin {
  async onload() {
    await this.loadSettings();
    addIcon("csdn-brand", CSDN_C_ICON_SVG);
    const draftStyle = document.createElement("style");
    draftStyle.setAttribute("data-csdn-draft-publisher", "true");
    draftStyle.textContent = CSDN_DRAFT_CSS;
    document.head.appendChild(draftStyle);
    this.register(() => draftStyle.remove());
    this.registerView(DRAFT_VIEW_TYPE, (leaf) => new CsdnDraftBoxView(leaf, this));

    if (this.settings.bridgeEnabled) {
      void this.startBridge().catch((error) => {
        new Notice(`桥接服务启动失败：${error.message}`, 10000);
      });
    }

    this.addCommand({
      id: "sync-current-note-to-csdn-draft",
      name: "同步当前笔记到 CSDN 草稿",
      checkCallback: (checking) => {
        const file = this.app.workspace.getActiveFile();
        const enabled = Boolean(file && file.extension === "md");
        if (!checking && enabled) void this.syncCurrentNote();
        return enabled;
      },
    });

    this.addCommand({
      id: "open-csdn-draft-box",
      name: "打开 CSDN 草稿箱管理",
      callback: () => void this.openDraftBox(),
    });

    this.addRibbonIcon("csdn-brand", "CSDN 草稿助手", (event) => {
      new Menu()
        .addItem((item) => item
          .setIcon("upload")
          .setTitle("同步当前笔记到 CSDN 草稿")
          .onClick(() => void this.syncCurrentNote()))
        .addItem((item) => item
          .setIcon("external-link")
          .setTitle("Open Current Note in CSDN Editor")
          .onClick(() => void this.openCurrentNoteInCsdnEditor()))
        .addItem((item) => item
          .setIcon("files")
          .setTitle("打开 CSDN 草稿箱管理")
          .onClick(() => void this.openDraftBox()))
        .showAtMouseEvent(event);
    });

    this.addSettingTab(new CsdnDraftPublisherSettingTab(this.app, this));
  }

  onunload() {
    this.stopManagedBridge();
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
    const accountState = normalizeAccounts(this.settings);
    this.settings.accounts = accountState.accounts;
    this.settings.activeAccountId = accountState.activeAccountId;
    await this.saveSettings();
  }

  async saveSettings() {
    await this.saveData(this.settings);
  }

  getAccount(accountId) {
    return this.settings.accounts.find((account) => account.id === accountId);
  }

  async addAccount(name) {
    const account = {
      id: `account-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name,
    };
    this.settings.accounts.push(account);
    this.settings.activeAccountId = account.id;
    return account;
  }

  async accountRequest(pathname, accountId, method = "GET") {
    const query = `?account_id=${encodeURIComponent(accountId)}`;
    const response = await requestUrl({
      url: `${this.settings.bridgeUrl}${pathname}${query}`,
      method,
      throw: false,
    });
    const result = JSON.parse(response.text || "{}");
    if (response.status < 200 || response.status >= 300 || !result.ok) {
      throw new Error(result.error || `桥接服务返回 HTTP ${response.status}`);
    }
    return result;
  }

  async listDrafts(accountId, page = 1, keyword = "") {
    const query = new URLSearchParams({
      account_id: accountId,
      page: String(page),
      page_size: "20",
      keyword,
    });
    const response = await requestUrl({
      url: `${this.settings.bridgeUrl}/drafts?${query.toString()}`,
      method: "GET",
      throw: false,
    });
    const result = JSON.parse(response.text || "{}");
    if (response.status < 200 || response.status >= 300 || !result.ok) {
      throw new Error(result.error || `桥接服务返回 HTTP ${response.status}`);
    }
    return result;
  }

  async getDraft(accountId, articleId) {
    const query = new URLSearchParams({
      account_id: accountId,
      article_id: articleId,
    });
    const response = await requestUrl({
      url: `${this.settings.bridgeUrl}/draft?${query.toString()}`,
      method: "GET",
      throw: false,
    });
    const result = JSON.parse(response.text || "{}");
    if (response.status < 200 || response.status >= 300 || !result.ok) {
      throw new Error(result.error || `桥接服务返回 HTTP ${response.status}`);
    }
    return result;
  }

  async deleteDraft(accountId, articleId) {
    const response = await requestUrl({
      url: `${this.settings.bridgeUrl}/drafts/delete`,
      method: "POST",
      contentType: "application/json",
      body: JSON.stringify({ account_id: accountId, article_id: articleId }),
      throw: false,
    });
    const result = JSON.parse(response.text || "{}");
    if (response.status < 200 || response.status >= 300 || !result.ok) {
      throw new Error(result.error || `桥接服务返回 HTTP ${response.status}`);
    }
    return result;
  }

  async importDraftToVault(item) {
    const account = this.getAccount(this.settings.activeAccountId) || DEFAULT_SETTINGS.accounts[0];
    const result = await this.getDraft(account.id, item.article_id);
    const folder = "CSDN草稿";
    if (!this.app.vault.getAbstractFileByPath(folder)) {
      await this.app.vault.createFolder(folder);
    }

    const articleId = asString(result.article_id || item.article_id);
    const title = asString(result.title || item.title || "未命名草稿");
    const markdown = [
      "---",
      "type: csdn-draft",
      "status: draft",
      `created: ${new Date().toISOString()}`,
      `updated: ${new Date().toISOString()}`,
      `csdn_article_id: ${articleId}`,
      `csdn_account_id: ${yamlString(result.account_id || account.id)}`,
      "---",
      "",
      `# ${title}`,
      "",
      asString(result.content).trim(),
      "",
    ].join("\n");

    let file = null;
    for (const candidate of this.app.vault.getMarkdownFiles()) {
      if (!candidate.path.startsWith(`${folder}/`)) continue;
      const candidateRaw = await this.app.vault.read(candidate);
      const candidateFrontmatter = parseFrontmatter(candidateRaw).data;
      if (asString(candidateFrontmatter.csdn_article_id) === articleId) {
        file = candidate;
        break;
      }
    }
    if (!file) {
      file = await this.app.vault.create(`${folder}/${safeDraftFileName(title, articleId)}`, markdown);
    } else {
      await this.app.vault.modify(file, markdown);
    }

    await this.app.workspace.getLeaf(false).openFile(file);
    new Notice(`已导入本地草稿：${file.path}\n编辑后可再次执行“同步当前笔记到 CSDN 草稿”回写。`, 8000);
    return file;
  }

  async openCurrentNoteInCsdnEditor() {
    const file = this.app.workspace.getActiveFile();
    if (!file || file.extension !== "md") {
      new Notice("请先打开一篇 Markdown 笔记。", 6000);
      return;
    }

    const notice = new Notice("正在打开 CSDN Markdown 编辑器…", 0);
    try {
      const raw = await this.app.vault.read(file);
      const parsed = parseFrontmatter(raw);
      const frontmatter = parsed.data;
      const metadata = this.app.metadataCache.getFileCache(file)?.frontmatter || {};
      const title = asString(frontmatter.title || metadata.title || firstHeading(parsed.body) || file.basename);
      const body = removeDuplicateTitle(parsed.body, title);
      const tags = normalizeList(frontmatter.tags || metadata.tags);
      const description = asString(frontmatter.description || frontmatter.summary || metadata.description);
      const cover = asString(frontmatter.cover || frontmatter.image || metadata.cover || metadata.image);
      const draftArticleId = asString(frontmatter.csdn_article_id || frontmatter.csdn_articleId);
      const draftAccountId = asString(frontmatter.csdn_account_id);
      const account = this.getAccount(draftAccountId || this.settings.activeAccountId) || DEFAULT_SETTINGS.accounts[0];

      const response = await requestUrl({
        url: `${this.settings.bridgeUrl}/open-editor`,
        method: "POST",
        contentType: "application/json",
        body: JSON.stringify({
          title,
          content: body,
          tags,
          description,
          cover,
          account_id: account.id,
          article_id: /^\d+$/.test(draftArticleId) ? draftArticleId : "",
        }),
        throw: false,
      });
      const result = JSON.parse(response.text || "{}");
      if (response.status < 200 || response.status >= 300 || !result.ok) {
        throw new Error(result.error || `桥接服务返回 HTTP ${response.status}`);
      }
      new Notice(`已在 CSDN 编辑器中打开“${title}”，请在浏览器中继续编辑并保存。`, 9000);
    } catch (error) {
      new Notice(`打开 CSDN 编辑器失败：${error.message}`, 10000);
    } finally {
      notice.hide();
    }
  }

  async openDraftBox() {
    const existing = this.app.workspace.getLeavesOfType(DRAFT_VIEW_TYPE)[0];
    if (existing) {
      this.app.workspace.revealLeaf(existing);
      return;
    }
    const leaf = this.app.workspace.getRightLeaf(false) || this.app.workspace.getLeaf(true);
    await leaf.setViewState({ type: DRAFT_VIEW_TYPE, active: true });
    this.app.workspace.revealLeaf(leaf);
  }

  async loginAccount(accountId) {
    return this.accountRequest("/login", accountId);
  }

  async sessionAccount(accountId) {
    return this.accountRequest("/session", accountId);
  }

  async logoutAccount(accountId) {
    return this.accountRequest("/logout", accountId, "POST");
  }

  getBridgeScriptPath() {
    const basePath = this.app.vault.adapter.basePath;
    if (!basePath) {
      throw new Error("无法定位当前 Vault 路径。");
    }
    return path.join(basePath, "tools", "csdn-draft-publisher", "csdn_bridge.py");
  }

  getBridgePort() {
    try {
      return String(new URL(this.settings.bridgeUrl).port || "8765");
    } catch {
      return "8765";
    }
  }

  async isBridgeAvailable() {
    try {
      await this.healthCheck();
      return true;
    } catch {
      return false;
    }
  }

  async waitForBridge(timeoutMs = 10000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      try {
        return await this.healthCheck();
      } catch {
        // Keep polling while the Python process is starting.
      }
      await new Promise((resolve) => window.setTimeout(resolve, 300));
    }
    return null;
  }

  getPythonCommands() {
    const candidates = [
      this.settings.pythonCommand,
      "C:\\Users\\hzb\\.conda\\envs\\csdn-publisher\\python.exe",
      "python",
      "py",
      "D:\\anaconda3\\python.exe",
    ].filter(Boolean);
    return [...new Set(candidates)];
  }

  launchBridgeProcess(command, scriptPath) {
    return new Promise((resolve, reject) => {
      const child = spawn(command, [
        scriptPath,
        "--host",
        "127.0.0.1",
        "--port",
        this.getBridgePort(),
      ], {
        cwd: path.dirname(scriptPath),
        windowsHide: true,
        stdio: "ignore",
      });

      const handleError = (error) => {
        child.removeListener("spawn", handleSpawn);
        reject(error);
      };
      const handleSpawn = () => {
        child.removeListener("error", handleError);
        resolve(child);
      };
      child.once("error", handleError);
      child.once("spawn", handleSpawn);
    });
  }

  async startBridge() {
    let existingHealth = null;
    try {
      existingHealth = await this.healthCheck();
    } catch {
      // The bridge is not responding; start it below if the toggle requested it.
    }
    if (existingHealth) {
      if (existingHealth.bridge_api_version !== BRIDGE_API_VERSION || existingHealth.account_profiles !== true) {
        throw new Error("检测到旧版桥接服务，请先关闭再重新打开“启用桥接服务”开关，以加载多账号版本。");
      }
      return { external: true, playwright: existingHealth.playwright };
    }

    if (this.bridgeProcess && !this.bridgeProcess.killed) {
      const health = await this.waitForBridge();
      if (health) {
        return { external: false, playwright: health.playwright };
      }
      throw new Error("桥接服务进程已存在，但未能响应健康检查。");
    }

    const scriptPath = this.getBridgeScriptPath();
    if (!fs.existsSync(scriptPath)) {
      throw new Error(`找不到桥接脚本：${scriptPath}`);
    }

    let child = null;
    let launchError = null;
    let launchedCommand = "";
    for (const command of this.getPythonCommands()) {
      try {
        child = await this.launchBridgeProcess(command, scriptPath);
        launchedCommand = command;
        break;
      } catch (error) {
        launchError = error;
      }
    }
    if (!child) {
      throw new Error(`无法启动 Python：${launchError?.message || "未找到可用的 Python 命令"}`);
    }

    this.bridgeProcess = child;
    this.bridgeProcessStartedByPlugin = true;
    child.once("error", (error) => {
      if (this.bridgeProcess === child) {
        this.bridgeProcess = null;
        this.bridgeProcessStartedByPlugin = false;
      }
      new Notice(`桥接服务进程错误：${error.message}`, 10000);
    });
    child.once("exit", () => {
      if (this.bridgeProcess === child) {
        this.bridgeProcess = null;
        this.bridgeProcessStartedByPlugin = false;
      }
    });

    const health = await this.waitForBridge();
    if (health?.playwright) {
      return { external: false, playwright: health.playwright };
    }

    this.stopManagedBridge();
    if (health && health.playwright === false) {
      throw new Error(`桥接服务已由 ${launchedCommand} 启动，但该 Python 环境未安装 Playwright。`);
    }
    throw new Error("桥接服务启动后未在 10 秒内响应，请检查 Python 和 Playwright 依赖。");
  }

  stopManagedBridge() {
    if (!this.bridgeProcessStartedByPlugin || !this.bridgeProcess) return;
    const child = this.bridgeProcess;
    this.bridgeProcess = null;
    this.bridgeProcessStartedByPlugin = false;
    try {
      child.kill();
    } catch (error) {
      // The process may have exited between the state check and kill().
    }
  }

  async healthCheck() {
    const response = await requestUrl({
      url: `${this.settings.bridgeUrl}/health`,
      method: "GET",
      throw: false,
    });
    if (response.status < 200 || response.status >= 300) {
      throw new Error(`HTTP ${response.status}`);
    }
    return JSON.parse(response.text);
  }

  async syncCurrentNote() {
    const file = this.app.workspace.getActiveFile();
    if (!file || file.extension !== "md") {
      new Notice("请先打开一篇 Markdown 笔记。");
      return;
    }

    const notice = new Notice("正在准备 CSDN 草稿…", 0);
    try {
      const raw = await this.app.vault.read(file);
      const parsed = parseFrontmatter(raw);
      const frontmatter = parsed.data;
      const metadata = this.app.metadataCache.getFileCache(file)?.frontmatter || {};
      const title = asString(frontmatter.title || metadata.title || firstHeading(parsed.body) || file.basename);
      const body = removeDuplicateTitle(parsed.body, title);
      const tags = normalizeList(frontmatter.tags || metadata.tags);
      const description = asString(frontmatter.description || frontmatter.summary || metadata.description);
      const cover = asString(frontmatter.cover || frontmatter.image || metadata.cover || metadata.image);
      const draftArticleId = asString(frontmatter.csdn_article_id || frontmatter.csdn_articleId);
      const draftAccountId = asString(frontmatter.csdn_account_id);
      const localImages = findLocalImages(body);
      const basePath = this.app.vault.adapter.basePath || "";
      const sourcePath = basePath ? `${basePath}/${file.path}` : file.path;
      const account = this.getAccount(draftAccountId || this.settings.activeAccountId) || DEFAULT_SETTINGS.accounts[0];

      const response = await requestUrl({
        url: `${this.settings.bridgeUrl}/sync`,
        method: "POST",
        contentType: "application/json",
        body: JSON.stringify({
          title,
          content: body,
          tags,
          description,
          cover,
          source_path: sourcePath,
          source_file: file.path,
          open_browser: this.settings.openBrowser,
          auto_save_wait_seconds: this.settings.autoSaveWaitSeconds,
          account_id: account.id,
          article_id: /^\d+$/.test(draftArticleId) ? draftArticleId : "",
        }),
        throw: false,
      });

      const result = JSON.parse(response.text || "{}");
      if (response.status < 200 || response.status >= 300 || !result.ok) {
        throw new Error(result.error || `桥接服务返回 HTTP ${response.status}`);
      }

      const warning = localImages.length
        ? `；检测到 ${localImages.length} 个本地图片引用，暂未自动上传`
        : "";
      if (result.saved) {
        const action = result.updated_existing ? "更新 CSDN 草稿" : "同步到 CSDN 草稿";
        new Notice(`已使用“${account.name}”${action}：${title}${warning}`, 8000);
      } else {
        new Notice(`“${account.name}”的正文已填入，但未确认 CSDN 保存状态，请在浏览器检查${warning}`, 10000);
      }
    } catch (error) {
      new Notice(`CSDN 同步失败：${error.message}`, 10000);
    } finally {
      notice.hide();
    }
  }
}

class CsdnDraftBoxView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
    this.page = 1;
    this.keyword = "";
    this.items = [];
    this.total = null;
    this.loading = false;
  }

  getViewType() {
    return DRAFT_VIEW_TYPE;
  }

  getDisplayText() {
    return "CSDN 草稿箱";
  }

  getIcon() {
    return DRAFT_VIEW_ICON;
  }

  async onOpen() {
    await this.render();
    await this.loadDrafts();
  }

  async onClose() {
    this.contentEl.empty();
  }

  activeAccount() {
    return this.plugin.getAccount(this.plugin.settings.activeAccountId)
      || DEFAULT_SETTINGS.accounts[0];
  }

  async render() {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.addClass("csdn-draft-box-view");
    const account = this.activeAccount();
    const shell = contentEl.createDiv({ cls: "csdn-draft-box-shell" });

    const hero = shell.createDiv({ cls: "csdn-draft-box-hero" });
    const heroCopy = hero.createDiv();
    heroCopy.createDiv({ text: "CSDN CONTENT", cls: "csdn-draft-box-eyebrow" });
    heroCopy.createEl("h2", { text: "草稿箱" });
    heroCopy.createEl("p", {
      text: "在 Obsidian 里整理、编辑，再把内容同步回 CSDN 草稿。",
      cls: "csdn-draft-box-subtitle",
    });
    hero.createDiv({ text: `当前账号 · ${account.name}`, cls: "csdn-draft-box-account" });

    const summary = shell.createDiv({ cls: "csdn-draft-box-summary" });
    const stats = [
      ["草稿总数", this.total === null ? (this.loading ? "—" : String(this.items.length)) : String(this.total)],
      ["当前页", this.loading ? "—" : `${this.items.length} 篇`],
      ["同步方式", "本地编辑"],
    ];
    for (const [label, value] of stats) {
      const stat = summary.createDiv({ cls: "csdn-draft-box-stat" });
      stat.createDiv({ text: label, cls: "csdn-draft-box-stat-label" });
      stat.createDiv({ text: value, cls: "csdn-draft-box-stat-value" });
    }

    const toolbar = shell.createDiv({ cls: "csdn-draft-box-toolbar" });
    const search = toolbar.createEl("input", {
      type: "search",
      placeholder: "搜索草稿标题",
      value: this.keyword,
      cls: "csdn-draft-box-search",
    });
    search.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        this.keyword = search.value.trim();
        this.page = 1;
        void this.loadDrafts();
      }
    });
    const searchButton = toolbar.createEl("button", { text: "搜索" });
    searchButton.addEventListener("click", () => {
      this.keyword = search.value.trim();
      this.page = 1;
      void this.loadDrafts();
    });
    const refreshButton = toolbar.createEl("button", { text: "刷新" });
    refreshButton.addEventListener("click", () => void this.loadDrafts());

    const list = shell.createDiv({ cls: "csdn-draft-box-list" });
    if (this.loading) {
      for (let index = 0; index < 6; index += 1) {
        list.createDiv({ cls: "csdn-draft-box-skeleton" });
      }
    } else if (!this.items.length) {
      list.createDiv({ text: "暂无草稿，或当前筛选没有匹配结果。", cls: "csdn-draft-box-state" });
    } else {
      for (const item of this.items) {
        const card = list.createDiv({ cls: "csdn-draft-box-card" });
        const top = card.createDiv({ cls: "csdn-draft-box-card-top" });
        top.createSpan({ text: "CSDN DRAFT", cls: "csdn-draft-box-badge" });
        top.createSpan({ text: item.updated_at || "最近更新" });
        card.createEl("h3", { text: item.title || "【无标题】" });
        card.createDiv({ text: `文章 ID · ${item.article_id}`, cls: "csdn-draft-box-card-meta" });
        const actions = card.createDiv({ cls: "csdn-draft-box-actions" });
        const edit = actions.createEl("button", { text: "导入到 Obsidian" });
        edit.addEventListener("click", () => void this.editDraft(item, edit));
        const remove = actions.createEl("button", { text: "删除" });
        remove.addClass("mod-warning");
        remove.addEventListener("click", () => void this.removeDraft(item));
      }
    }

    const pager = shell.createDiv({ cls: "csdn-draft-box-pager" });
    const previous = pager.createEl("button", { text: "上一页" });
    previous.disabled = this.loading || this.page <= 1;
    previous.addEventListener("click", () => {
      if (this.page > 1) {
        this.page -= 1;
        void this.loadDrafts();
      }
    });
    pager.createSpan({ text: `第 ${this.page} 页` });
    const next = pager.createEl("button", { text: "下一页" });
    next.disabled = this.loading || this.items.length < 20;
    next.addEventListener("click", () => {
      if (this.items.length >= 20) {
        this.page += 1;
        void this.loadDrafts();
      }
    });
  }

  async editDraft(item, button) {
    button.textContent = "读取中…";
    button.disabled = true;
    try {
      await this.plugin.importDraftToVault(item);
    } catch (error) {
      new Notice(`导入 CSDN 草稿失败：${error.message}`, 10000);
    } finally {
      button.textContent = "导入到 Obsidian";
      button.disabled = false;
    }
  }

  async loadDrafts() {
    if (this.loading) return;
    this.loading = true;
    await this.render();
    try {
      const account = this.activeAccount();
      const result = await this.plugin.listDrafts(account.id, this.page, this.keyword);
      this.items = Array.isArray(result.items) ? result.items : [];
      this.total = Number.isFinite(Number(result.total)) ? Number(result.total) : null;
    } catch (error) {
      this.items = [];
      this.total = null;
      new Notice(`读取 CSDN 草稿箱失败：${error.message}`, 10000);
    } finally {
      this.loading = false;
      await this.render();
    }
  }

  async removeDraft(item) {
    const account = this.activeAccount();
    const confirmed = window.confirm(`确定删除 CSDN 草稿“${item.title || "【无标题】"}”吗？此操作不可恢复。`);
    if (!confirmed) return;
    try {
      await this.plugin.deleteDraft(account.id, item.article_id);
      new Notice(`已删除草稿：${item.title || "【无标题】"}`, 6000);
      await this.loadDrafts();
    } catch (error) {
      new Notice(`删除 CSDN 草稿失败：${error.message}`, 10000);
    }
  }
}

module.exports = CsdnDraftPublisher;
