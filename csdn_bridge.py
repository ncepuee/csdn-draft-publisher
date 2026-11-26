"""Local Playwright bridge for syncing an Obsidian Markdown note to a CSDN draft.

This service deliberately never clicks a button whose accessible name contains
"发布". CSDN's private editor DOM changes over time, so selectors are grouped
as fallbacks and failures are reported instead of silently publishing.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


def _default_app_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / "CSDN-Draft-Publisher"


HOST = "127.0.0.1"
PORT = 8765
BRIDGE_API_VERSION = "0.8.0"
EDITOR_URL = "https://editor.csdn.net/md/"
MANAGE_URL = "https://mp.csdn.net/mp_blog/manage/article"
LOGIN_URL = "https://passport.csdn.net/login?code=applets"
CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/134.0.0.0 Safari/537.36"
)
APP_DATA_DIR = _default_app_data_dir()
PROFILE_DIR = APP_DATA_DIR / "playwright-profile"
PROFILE_ROOT = APP_DATA_DIR / "profiles"
LOG_FILE = APP_DATA_DIR / "bridge.log"
SYNC_LOCK = threading.Lock()
ACCOUNT_STATE_LOCK = threading.Lock()
ACCOUNT_STATES: dict[str, dict[str, Any]] = {}
EDITOR_SESSIONS_LOCK = threading.Lock()
EDITOR_SESSIONS: dict[str, tuple[Any, Any, Any, str]] = {}
QR_SESSIONS_LOCK = threading.Lock()
QR_SESSIONS: dict[str, dict[str, Any]] = {}


def log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as file:
            file.write(line + "\n")
    except OSError:
        pass


def normalize_account_id(account_id: str | None) -> str:
    value = str(account_id or "default").strip()
    if value == "default":
        return value
    if not re.fullmatch(r"account-[A-Za-z0-9_-]+", value):
        raise ValueError("无效的 CSDN 账号标识")
    return value


def profile_dir_for_account(account_id: str | None) -> Path:
    normalized = normalize_account_id(account_id)
    if normalized == "default":
        return PROFILE_DIR
    return PROFILE_ROOT / normalized


def account_state(account_id: str | None) -> dict[str, Any]:
    normalized = normalize_account_id(account_id)
    profile_dir = profile_dir_for_account(normalized)
    with ACCOUNT_STATE_LOCK:
        state = dict(ACCOUNT_STATES.get(normalized, {
            "status": "unknown",
            "message": "尚未检查登录态",
            "updated_at": None,
        }))
    state.update({
        "account_id": normalized,
        "profile_dir": str(profile_dir),
        "profile_exists": profile_dir.exists(),
    })
    return state


def set_account_state(account_id: str | None, status: str, message: str) -> None:
    normalized = normalize_account_id(account_id)
    with ACCOUNT_STATE_LOCK:
        ACCOUNT_STATES[normalized] = {
            "status": status,
            "message": message,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }


def normalize_lang(lang: str | None) -> str:
    value = str(lang or "zh").strip().lower()
    return "en" if value.startswith("en") else "zh"


_EN_EXACT_MESSAGES: dict[str, str] = {
    "无效的 CSDN 账号标识": "Invalid CSDN account identifier.",
    "尚未检查登录态": "Session status has not been checked yet.",
    "未找到可用的 Chromium / Chrome / Edge 浏览器内核。请在插件设置中点击“安装浏览器内核”，或执行：python -m playwright install chromium": (
        "No Chromium / Chrome / Edge browser binary found. Click 'Install browser kernel' in plugin settings, "
        "or run: python -m playwright install chromium"
    ),
    "CSDN 登录未完成或已超时，请先在助手浏览器中完成登录。": "CSDN sign-in timed out or was not completed. Please finish signing in first.",
    "未检测到 CSDN 编辑器控件，请确认已登录并使用 Markdown 编辑器。": "CSDN Markdown editor controls were not detected. Please verify your login state.",
    "当前账号登录态未生效或已过期，请点击“扫码登录”重新登录。": "Session is missing or expired for this account. Click 'QR Login' to sign in.",
    "CSDN 登录未完成或已超时，请先点击“扫码登录”完成登录。": "CSDN sign-in timed out or was not completed. Click 'QR Login' to sign in.",
    "未检测到 CSDN 内容管理页面，请确认已登录。": "CSDN article management page was not detected. Please verify your login state.",
    "CSDN 内容管理页面未加载完整，无法定位草稿箱标签页。": "CSDN management page did not finish loading; could not locate the Drafts tab.",
    "当前账号尚未登录或登录已过期，请点击“扫码登录”完成登录。": "This account is not signed in or its session has expired. Click 'QR Login' to sign in.",
    "尚未登录（本地无登录缓存）": "Not signed in (no local browser profile yet)",
    "未安装 Playwright，无法验证登录态": "Playwright is not installed; unable to verify session",
    "尚未登录或登录态已失效，请扫码登录": "Not signed in or session expired. Please sign in via QR code",
    "登录态已失效，请重新扫码登录": "Session expired. Please sign in again via QR code",
    "登录态有效（CSDN 内容管理后台已连通）": "Session is active (connected to CSDN article console)",
    "未安装 Playwright，请先安装依赖。": "Playwright is not installed. Please install dependencies first.",
    "未安装 Playwright。请在终端执行：pip install playwright && python -m playwright install chromium": (
        "Playwright is not installed. Run: pip install playwright && python -m playwright install chromium"
    ),
    "CSDN 草稿搜索请求超时，请稍后重试。": "CSDN draft search timed out. Please try again.",
    "未找到 CSDN 草稿搜索框。": "Could not locate the CSDN draft search input.",
    "CSDN 草稿分页请求超时，请稍后重试。": "CSDN draft pagination timed out. Please try again.",
    "无效的 CSDN 草稿文章 ID": "Invalid CSDN draft article ID.",
    "CSDN 草稿内容为空或尚未加载完成。": "CSDN draft content is empty or has not finished loading.",
    "未找到要删除的草稿，可能已被删除或列表已变化。": "Could not find the draft to delete; it may have already been removed.",
    "未找到 CSDN 草稿删除入口。": "Could not locate the delete action for this CSDN draft.",
    "CSDN 删除失败": "Failed to delete CSDN draft.",
    "文章标题为空": "Article title is empty.",
    "文章正文为空": "Article body is empty.",
    "未找到摘要输入框": "Summary input box not found on CSDN page",
    "标签已读取但暂未自动选择，需在 CSDN 页面确认": "Tags read from frontmatter; please confirm tag selection on CSDN",
    "封面已读取但暂未自动上传，需在 CSDN 页面确认": "Cover read from frontmatter; please confirm cover upload on CSDN",
    "未发现保存按钮或保存成功提示，可能需要在页面手动确认": "Save confirmation signal not detected; please double-check in the browser",
    "该账号的 CSDN 编辑器窗口已经打开，请直接继续编辑。": "A CSDN editor window is already open for this account. Please continue editing there.",
    "登录窗口运行中，请在浏览器中完成 CSDN 登录": "Browser sign-in window is open. Please complete CSDN sign-in there.",
    "登录态已清除": "Saved session cleared.",
    "已有同步任务正在运行，请稍后再试": "Another sync task is currently running. Please try again shortly.",
    "尚未启动扫码登录": "QR login has not been started.",
    "二维码登录进行中": "QR code login in progress",
    "正在获取 CSDN 二维码…": "Fetching CSDN QR code…",
    "未能从 CSDN 登录页提取到二维码，请点击刷新或改用浏览器窗口登录。": (
        "Could not extract QR code from CSDN login page. Click Refresh or switch to Browser Login."
    ),
    "请使用 CSDN APP 扫一扫登录": "Scan with the CSDN App to sign in",
    "请使用微信扫一扫登录": "Scan with WeChat to sign in",
    "已取消扫码登录": "QR login cancelled",
    "扫码登录已超时，请点击刷新重试": "QR login timed out. Click Refresh to try again",
    "已扫码，请在手机上点击确认登录…": "QR code scanned. Please confirm sign-in on your phone…",
    "CSDN 要求补充手机号绑定或安全验证，请点击“改用浏览器登录”完成首次验证。": (
        "CSDN requires phone binding or security verification. Click 'Use Browser Login' to complete it once."
    ),
    "二维码已过期，请点击“刷新二维码”": "QR code expired. Click 'Refresh QR' to get a new one",
    "登录成功，正在同步草稿箱会话…": "Signed in! Syncing draft console session…",
    "登录成功！已保存该账号登录态": "Signed in! Session saved for this account",
    "已通过扫码完成 CSDN 登录": "Signed in to CSDN via QR code",
    "扫码已完成，但未检测到 CSDN 认证 Cookie，请重试或改用浏览器登录。": (
        "QR scan finished, but CSDN authentication cookies were not detected. Please retry or use Browser Login."
    ),
    "正在启动扫码登录…": "Starting QR login…",
    "正在切换二维码…": "Switching QR mode…",
    "正在刷新二维码…": "Refreshing QR code…",
    "登录窗口已关闭。": "Browser sign-in window was closed.",
    "CSDN 登录未完成或已超时。": "CSDN sign-in timed out or was not completed.",
}

_EN_REGEX_MESSAGES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"^当前已登录 CSDN 账号：(.+?)。如需切换账号或重新扫码，请点击“重新扫码”。$"),
        r"Signed in as: \1. Click 'Re-scan / Switch Account' to sign in with another account.",
    ),
    (re.compile(r"^已登录（(.+?)）$"), r"Signed in (\1)"),
    (re.compile(r"^登录态检查失败：([\s\S]+)$"), r"Session check failed: \1"),
    (
        re.compile(r"^找不到 CSDN 编辑器控件；已尝试 (\d+) 个选择器。([\s\S]*)$"),
        r"Could not locate CSDN editor controls after trying \1 selectors. \2",
    ),
    (re.compile(r"^CSDN 删除接口返回 HTTP (\d+)$"), r"CSDN delete API returned HTTP \1"),
]


def translate_bridge_text(text: str, lang: str) -> str:
    if lang != "en" or not text:
        return text
    exact = _EN_EXACT_MESSAGES.get(text)
    if exact is not None:
        return exact
    for pattern, repl in _EN_REGEX_MESSAGES:
        if pattern.match(text):
            return pattern.sub(repl, text)
    return text


def localize_payload(payload: dict[str, Any], lang: str) -> dict[str, Any]:
    if lang != "en":
        return payload
    out = dict(payload)
    for key in ("message", "error"):
        if isinstance(out.get(key), str):
            out[key] = translate_bridge_text(out[key], lang)
    if isinstance(out.get("warnings"), list):
        out["warnings"] = [
            translate_bridge_text(w, lang) if isinstance(w, str) else w
            for w in out["warnings"]
        ]
    if isinstance(out.get("title"), str) and out["title"] == "【无标题】":
        out["title"] = "[Untitled]"
    if isinstance(out.get("items"), list):
        localized_items = []
        for item in out["items"]:
            if isinstance(item, dict) and item.get("title") == "【无标题】":
                copied = dict(item)
                copied["title"] = "[Untitled]"
                localized_items.append(copied)
            else:
                localized_items.append(item)
        out["items"] = localized_items
    return out


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    lang = getattr(handler, "_request_lang", "zh")
    body = json.dumps(localize_payload(payload, lang), ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "app://obsidian.md")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)


def has_playwright() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def launch_browser_context(
    playwright: Any,
    user_data_dir: str | Path,
    *,
    headless: bool = False,
    viewport: dict[str, int] | None = None,
    permissions: list[str] | None = None,
) -> Any:
    """Launch a persistent Chromium context with automatic fallback to Chrome/Edge when Playwright's browser binaries are not installed."""
    base_kwargs: dict[str, Any] = {
        "user_data_dir": str(user_data_dir),
        "headless": headless,
        "viewport": viewport or {"width": 1440, "height": 1000},
    }
    if permissions:
        base_kwargs["permissions"] = permissions
    if headless:
        base_kwargs["user_agent"] = CHROME_USER_AGENT

    attempts: list[dict[str, Any]] = []
    if headless:
        # Prefer full Chrome / Edge in headless mode: CSDN's gateway drops
        # Playwright's stripped-down chrome-headless-shell with ERR_CONNECTION_CLOSED
        # once authentication cookies are present.
        attempts.append({"channel": "chrome"})
        attempts.append({"channel": "msedge"})
        try:
            full_exe = playwright.chromium.executable_path
            if full_exe and Path(full_exe).exists():
                attempts.append({"executable_path": full_exe, "args": ["--headless=new"]})
        except Exception:
            pass
        attempts.append({})
    else:
        attempts.append({})
        attempts.append({"channel": "chrome"})
        attempts.append({"channel": "msedge"})

    first_error: Exception | None = None
    for extra in attempts:
        try:
            return playwright.chromium.launch_persistent_context(**base_kwargs, **extra)
        except Exception as error:
            if first_error is None:
                first_error = error
            msg = str(error)
            if (
                "Executable doesn't exist" not in msg
                and "is not found" not in msg
                and "Chromium distribution" not in msg
            ):
                raise
    raise RuntimeError(
        "未找到可用的 Chromium / Chrome / Edge 浏览器内核。"
        "请在插件设置中点击“安装浏览器内核”，或执行：python -m playwright install chromium"
    ) from first_error


def selector_candidates(page: Any, candidates: list[str], timeout: int = 15000) -> Any:
    last_error = None
    for selector in candidates:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=timeout)
            return locator
        except Exception as error:  # selectors are intentionally best-effort fallbacks
            last_error = error
    raise RuntimeError(f"找不到 CSDN 编辑器控件；已尝试 {len(candidates)} 个选择器。{last_error}")


def find_title_input(page: Any) -> Any:
    return selector_candidates(page, [
        'input.article-bar__title',
        '.article-bar__input-box input',
        'input[placeholder*="文章标题"]',
        'input[placeholder*="标题"]',
        'input#articleContentId',
        'div.article-bar input',
        'input[type="text"]',
    ])


def find_editor(page: Any) -> Any:
    return selector_candidates(page, [
        '.editor__inner[contenteditable="true"]',
        'div.editor div.cledit-section',
        'div.cledit-section',
        'pre.editor__inner',
        '.CodeMirror',
        '[contenteditable="true"]',
        'textarea',
    ], timeout=20000)


def fill_editor(page: Any, content: str) -> None:
    editor = find_editor(page)
    tag_name = editor.evaluate("el => el.tagName.toLowerCase()")
    if tag_name == "textarea":
        editor.fill(content)
        return

    editor.click()
    editor.evaluate(
        """
        (element, markdown) => {
          element.focus();
          const range = document.createRange();
          range.selectNodeContents(element);
          const selection = window.getSelection();
          selection?.removeAllRanges();
          selection?.addRange(range);
          document.execCommand('delete', false);

          let handled = false;
          if (typeof DataTransfer !== 'undefined' && typeof ClipboardEvent !== 'undefined') {
            const clipboardData = new DataTransfer();
            clipboardData.setData('text/plain', markdown);
            const event = new ClipboardEvent('paste', {
              bubbles: true,
              cancelable: true,
              clipboardData,
            });
            element.dispatchEvent(event);
            handled = event.defaultPrevented;
          }
          if (!handled) {
            handled = document.execCommand('insertText', false, markdown);
          }
          if (!handled) element.textContent = markdown;
          element.dispatchEvent(new InputEvent('input', { bubbles: true }));
          element.dispatchEvent(new Event('change', { bubbles: true }));
        }
        """,
        content,
    )


def fill_title(page: Any, title: str) -> None:
    # Current CSDN renders a display div and keeps the actual input hidden
    # until the display is clicked. This mirrors the working CSDN Sync flow.
    display = page.locator(".article-bar__title-display").first
    try:
        display.wait_for(state="visible", timeout=5000)
        display.click()
    except Exception:
        pass

    for selector in [
        "input.article-bar__title",
        ".article-bar__input-box input",
        'input[placeholder*="文章标题"]',
        'input[placeholder*="标题"]',
        "input#articleContentId",
    ]:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="attached", timeout=5000)
            locator.evaluate(
                """
                (input, value) => {
                  input.removeAttribute('aria-hidden');
                  input.removeAttribute('style');
                  const setter = Object.getOwnPropertyDescriptor(
                    HTMLInputElement.prototype, 'value'
                  )?.set;
                  setter?.call(input, value);
                  input.dispatchEvent(new Event('input', { bubbles: true }));
                  input.dispatchEvent(new Event('change', { bubbles: true }));
                }
                """,
                title,
            )
            return
        except Exception:
            continue
    # Fall back to the original title locator for older CSDN editor variants.
    find_title_input(page).fill(title)


def fill_optional(page: Any, selectors: list[str], value: str) -> bool:
    if not value:
        return False
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=2500)
            locator.fill(value)
            return True
        except Exception:
            continue
    return False


def visible_button_texts(page: Any) -> list[str]:
    try:
        return [text.strip() for text in page.locator("button").all_text_contents() if text.strip()]
    except Exception:
        return []


def click_save_button(page: Any) -> str | None:
    # Never broaden this matcher to include "发布". A draft assistant must be
    # safe when CSDN changes the wording of its publish dialog.
    patterns = [
        re.compile(r"^保存草稿$"),
        re.compile(r"保存草稿"),
        re.compile(r"^保存$"),
        re.compile(r"保存文章"),
    ]
    for pattern in patterns:
        buttons = page.get_by_role("button", name=pattern).all()
        for button in buttons:
            try:
                label = (button.inner_text() or "").strip()
                if "发布" in label:
                    continue
                button.click()
                return label or "保存"
            except Exception:
                continue
    return None


def page_has_saved_signal(page: Any) -> bool:
    try:
        text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        return False
    return bool(re.search(r"保存成功|已保存|自动保存|草稿已", text, re.I))


def wait_for_login_if_needed(page: Any) -> None:
    # The editor may keep editor.csdn.net in the URL while showing a login
    # overlay. Wait for an actual editor control instead of relying on URL text.
    selectors = [
        '.article-bar__title-display',
        'input.article-bar__title',
        '.editor__inner[contenteditable="true"]',
        'input[placeholder*="文章标题"]',
    ]
    try:
        page.wait_for_selector(", ".join(selectors), state="visible", timeout=180000)
    except Exception as error:
        if "passport.csdn.net" in page.url or "login" in page.url.lower():
            raise RuntimeError("CSDN 登录未完成或已超时，请先在助手浏览器中完成登录。") from error
        raise RuntimeError("未检测到 CSDN 编辑器控件，请确认已登录并使用 Markdown 编辑器。") from error


def auth_cookie_username(context: Any) -> str:
    try:
        cookies = context.cookies([
            "https://www.csdn.net",
            "https://mp.csdn.net",
            "https://editor.csdn.net",
            "https://passport.csdn.net",
        ])
    except Exception:
        return ""
    names = {c.get("name"): str(c.get("value") or "").strip() for c in cookies}
    if not (names.get("UserToken") and names.get("UserName")):
        return ""
    raw = names.get("UserNick") or names.get("UserName") or ""
    try:
        return unquote(raw)
    except Exception:
        return raw


def has_auth_cookies(context: Any) -> bool:
    """Return True only when CSDN's real authentication cookies (UserToken & UserName) exist."""
    return bool(auth_cookie_username(context))


def _visible_manage_tabs(page: Any) -> list[Any]:
    result: list[Any] = []
    for selector in ('[role="tab"]', ".nav-link", ".el-tabs__item"):
        loc = page.locator(selector)
        try:
            cnt = loc.count()
        except Exception:
            continue
        for idx in range(cnt):
            item = loc.nth(idx)
            try:
                if item.is_visible():
                    result.append(item)
            except Exception:
                continue
        if result:
            return result
    return result


def wait_for_manage_page(page: Any, *, headless: bool = False) -> None:
    timeout_sec = 25.0 if headless else 180.0
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        current_url = (page.url or "").lower()
        if headless and ("passport.csdn.net" in current_url or "/login" in current_url):
            raise RuntimeError("当前账号登录态未生效或已过期，请点击“扫码登录”重新登录。")
        if _visible_manage_tabs(page):
            return
        page.wait_for_timeout(400)
    if "passport.csdn.net" in (page.url or "").lower() or "login" in (page.url or "").lower():
        raise RuntimeError("CSDN 登录未完成或已超时，请先点击“扫码登录”完成登录。")
    raise RuntimeError("未检测到 CSDN 内容管理页面，请确认已登录。")


def wait_for_article_results(page: Any) -> None:
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        for selector in (".article-list-item-mp", ".el_mcm-pagination", ".no-data-box", ".empty-box"):
            loc = page.locator(selector)
            try:
                for idx in range(min(loc.count(), 5)):
                    if loc.nth(idx).is_visible():
                        return
            except Exception:
                continue
        page.wait_for_timeout(300)


def article_list_response(response: Any, status: str = "draft") -> bool:
    return (
        "/blog/phoenix/console/v1/article/list" in response.url
        and (f"status={status}" in response.url or status == "")
        and response.request.method == "GET"
    )


def extract_article_id(url: str) -> str | None:
    for pattern in (r"[?&]articleId=(\d+)", r"/editor/(\d+)", r"/details/(\d+)"):
        match = re.search(pattern, url or "")
        if match:
            return match.group(1)
    return None


def find_drafts_tab(page: Any) -> Any:
    for item in _visible_manage_tabs(page):
        try:
            text = (item.inner_text() or "").strip()
            if "草稿" in text:
                return item
        except Exception:
            continue
    visible_tabs = _visible_manage_tabs(page)
    if len(visible_tabs) >= 5:
        return visible_tabs[4]
    raise RuntimeError("CSDN 内容管理页面未加载完整，无法定位草稿箱标签页。")


def manage_page_for_account(
    playwright: Any,
    account_id: str,
    headless: bool = False,
) -> tuple[Any, Any]:
    profile_dir = profile_dir_for_account(account_id)
    profile_dir.mkdir(parents=True, exist_ok=True)
    context = launch_browser_context(
        playwright,
        profile_dir,
        headless=headless,
        viewport={"width": 1440, "height": 1000},
        permissions=["clipboard-read", "clipboard-write"],
    )
    try:
        if headless and not has_auth_cookies(context):
            raise RuntimeError("当前账号尚未登录或登录已过期，请点击“扫码登录”完成登录。")
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(MANAGE_URL, wait_until="domcontentloaded", timeout=60000)
        wait_for_manage_page(page, headless=headless)
        return context, page
    except Exception:
        context.close()
        raise


def verify_account_session(account_id: str) -> dict[str, Any]:
    """Silently check whether the saved Playwright profile still has a valid CSDN session."""
    normalized = normalize_account_id(account_id)
    profile_dir = profile_dir_for_account(normalized)
    if not profile_dir.exists():
        set_account_state(normalized, "logged_out", "尚未登录（本地无登录缓存）")
        return account_state(normalized)
    if not has_playwright():
        set_account_state(normalized, "error", "未安装 Playwright，无法验证登录态")
        return account_state(normalized)

    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as playwright:
            context = launch_browser_context(
                playwright,
                profile_dir,
                headless=True,
                viewport={"width": 1440, "height": 1000},
            )
            try:
                if not has_auth_cookies(context):
                    set_account_state(normalized, "logged_out", "尚未登录或登录态已失效，请扫码登录")
                    return account_state(normalized)
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(MANAGE_URL, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(2000)
                if "passport.csdn.net" in (page.url or "").lower() or "/login" in (page.url or "").lower():
                    set_account_state(normalized, "logged_out", "登录态已失效，请重新扫码登录")
                else:
                    set_account_state(normalized, "logged_in", "登录态有效（CSDN 内容管理后台已连通）")
            finally:
                context.close()
    except Exception as error:
        set_account_state(normalized, "error", f"登录态检查失败：{error}")
    return account_state(normalized)


def _parse_drafts_from_api_body(api_body: dict[str, Any] | None) -> tuple[list[dict[str, Any]] | None, int | None]:
    if not isinstance(api_body, dict) or api_body.get("code") != 200:
        return None, None
    data = api_body.get("data")
    if not isinstance(data, dict):
        return None, None
    raw_list = data.get("list")
    if not isinstance(raw_list, list):
        return None, None
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in raw_list:
        if not isinstance(entry, dict):
            continue
        article_id = str(entry.get("articleId") or entry.get("id") or "").strip()
        if not article_id or article_id in seen:
            continue
        seen.add(article_id)
        title = str(entry.get("title") or "").strip() or "【无标题】"
        updated_at = str(
            entry.get("postTime")
            or entry.get("updateTime")
            or entry.get("formatTime")
            or ""
        ).strip()
        items.append({
            "article_id": article_id,
            "title": title,
            "edit_url": f"https://editor.csdn.net/md/?articleId={article_id}",
            "updated_at": updated_at,
        })
    total_raw = data.get("total")
    total = int(total_raw) if isinstance(total_raw, (int, float)) or (isinstance(total_raw, str) and total_raw.isdigit()) else len(items)
    return items, total


def read_drafts(payload: dict[str, Any]) -> dict[str, Any]:
    if not has_playwright():
        raise RuntimeError("未安装 Playwright，请先安装依赖。")
    from playwright.sync_api import sync_playwright

    account_id = normalize_account_id(payload.get("account_id"))
    page_number = max(1, min(int(payload.get("page", 1)), 1000))
    keyword = str(payload.get("keyword", "")).strip()
    page_size = max(1, min(int(payload.get("page_size", 20)), 50))
    headless = str(payload.get("headless", "true")).lower() not in ("0", "false", "no")

    with sync_playwright() as playwright:
        context, page = manage_page_for_account(playwright, account_id, headless=headless)
        try:
            last_api_body: dict[str, Any] | None = None

            def capture_list_response(resp: Any) -> None:
                nonlocal last_api_body
                if "/blog/phoenix/console/v1/article/list" in resp.url and resp.request.method == "GET":
                    try:
                        last_api_body = resp.json()
                    except Exception:
                        pass

            page.on("response", capture_list_response)
            drafts_tab = find_drafts_tab(page)
            try:
                with page.expect_response(
                    lambda response: article_list_response(response),
                    timeout=30000,
                ) as resp_info:
                    drafts_tab.click()
                try:
                    last_api_body = resp_info.value.json()
                except Exception:
                    pass
            except Exception:
                # Tab may already be active or use a slightly different query param; give XHR a moment.
                page.wait_for_timeout(2000)
            wait_for_article_results(page)

            search = page.locator('input[placeholder*="标题关键词"], input[placeholder*="关键词"]').first
            if keyword and search.count():
                search.fill(keyword)
                try:
                    with page.expect_response(
                        lambda response: article_list_response(response, status=""),
                        timeout=30000,
                    ) as resp_info:
                        page.get_by_role("button", name="搜索").click()
                    try:
                        last_api_body = resp_info.value.json()
                    except Exception:
                        pass
                except Exception as error:
                    raise RuntimeError("CSDN 草稿搜索请求超时，请稍后重试。") from error
                wait_for_article_results(page)
            elif keyword:
                raise RuntimeError("未找到 CSDN 草稿搜索框。")

            if page_number > 1:
                for _ in range(page_number - 1):
                    next_button = page.get_by_role("button", name="下一页")
                    if not next_button.count() or not next_button.is_enabled():
                        break
                    try:
                        with page.expect_response(
                            lambda response: article_list_response(response, status=""),
                            timeout=30000,
                        ) as resp_info:
                            next_button.click()
                        try:
                            last_api_body = resp_info.value.json()
                        except Exception:
                            pass
                    except Exception as error:
                        raise RuntimeError("CSDN 草稿分页请求超时，请稍后重试。") from error
                    wait_for_article_results(page)

            api_items, api_total = _parse_drafts_from_api_body(last_api_body)
            if api_items is not None:
                items = api_items
                draft_count = api_total
            else:
                links = page.locator(
                    'a[href*="articleId="], a[href*="/creation/editor/"], .article-list-item-mp a'
                )
                items = []
                seen: set[str] = set()
                for index in range(links.count()):
                    link = links.nth(index)
                    href = link.get_attribute("href") or ""
                    article_id = extract_article_id(href)
                    title = (link.inner_text() or "").strip()
                    if not article_id or article_id in seen or not title or title in ("编辑", "删除", "浏览"):
                        continue
                    seen.add(article_id)
                    item = link.locator("xpath=ancestor::div[contains(@class, 'article-list-item-mp')][1]").first
                    item_text = item.inner_text() if item.count() else ""
                    time_match = re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", item_text)
                    items.append({
                        "article_id": article_id,
                        "title": title,
                        "edit_url": f"https://editor.csdn.net/md/?articleId={article_id}",
                        "updated_at": time_match.group(0) if time_match else "",
                    })
                draft_count = None

            if draft_count is None:
                try:
                    draft_count_match = re.search(r"\((\d+)\)", drafts_tab.inner_text())
                    draft_count = int(draft_count_match.group(1)) if draft_count_match else len(items)
                except Exception:
                    draft_count = len(items)
            return {
                "ok": True,
                "account_id": account_id,
                "items": items,
                "page": page_number,
                "page_size": page_size,
                "total": draft_count,
                "keyword": keyword,
                "profile_dir": str(profile_dir_for_account(account_id)),
            }
        finally:
            context.close()


def read_draft(payload: dict[str, Any]) -> dict[str, Any]:
    if not has_playwright():
        raise RuntimeError("未安装 Playwright，请先安装依赖。")
    from playwright.sync_api import sync_playwright

    account_id = normalize_account_id(payload.get("account_id"))
    article_id = str(payload.get("article_id", "")).strip()
    if not re.fullmatch(r"\d+", article_id):
        raise ValueError("无效的 CSDN 草稿文章 ID")

    profile_dir = profile_dir_for_account(account_id)
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = launch_browser_context(
            playwright,
            profile_dir,
            headless=True,
            viewport={"width": 1440, "height": 1000},
            permissions=["clipboard-read", "clipboard-write"],
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(f"{EDITOR_URL}?articleId={article_id}", wait_until="domcontentloaded", timeout=60000)
            wait_for_login_if_needed(page)
            page.wait_for_timeout(1500)
            title_input = page.locator("input.article-bar__title").first
            editor = page.locator('.editor__inner[contenteditable="true"]').first
            title_input.wait_for(state="attached", timeout=30000)
            editor.wait_for(state="visible", timeout=30000)
            title = (title_input.input_value() or "").strip()
            content = editor.inner_text()
            if not title and not content.strip():
                raise RuntimeError("CSDN 草稿内容为空或尚未加载完成。")
            return {
                "ok": True,
                "account_id": account_id,
                "article_id": article_id,
                "title": title or "【无标题】",
                "content": content,
                "edit_url": f"{EDITOR_URL}?articleId={article_id}",
                "profile_dir": str(profile_dir),
            }
        finally:
            context.close()


def delete_draft(payload: dict[str, Any]) -> dict[str, Any]:
    if not has_playwright():
        raise RuntimeError("未安装 Playwright，请先安装依赖。")
    from playwright.sync_api import sync_playwright

    account_id = normalize_account_id(payload.get("account_id"))
    article_id = str(payload.get("article_id", "")).strip()
    if not re.fullmatch(r"\d+", article_id):
        raise ValueError("无效的 CSDN 草稿文章 ID")

    with sync_playwright() as playwright:
        context, page = manage_page_for_account(playwright, account_id, headless=True)
        try:
            find_drafts_tab(page).click()
            page.wait_for_timeout(1000)
            row = page.locator(
                ".article-list-item-mp",
            ).filter(has=page.locator(f'a[href*="articleId={article_id}"]')).first
            if not row.count():
                raise RuntimeError("未找到要删除的草稿，可能已被删除或列表已变化。")
            delete_link = row.locator("a").filter(has_text="删除").first
            if not delete_link.count():
                raise RuntimeError("未找到 CSDN 草稿删除入口。")
            delete_link.click()
            confirm = page.get_by_role("button", name="确定").last
            confirm.wait_for(state="visible", timeout=10000)
            with page.expect_response(
                lambda response: "/blog/phoenix/console/v1/article/del" in response.url
                and response.request.method == "POST",
                timeout=30000,
            ) as response_info:
                confirm.click()
            response = response_info.value
            if response.status != 200:
                raise RuntimeError(f"CSDN 删除接口返回 HTTP {response.status}")
            body = json.loads(response.text() or "{}")
            if body.get("code") != 200:
                data = body.get("data") or {}
                raise RuntimeError(body.get("message") or data.get("message") or "CSDN 删除失败")
            return {"ok": True, "account_id": account_id, "article_id": article_id}
        finally:
            context.close()


def sync_to_csdn(payload: dict[str, Any]) -> dict[str, Any]:
    if not has_playwright():
        raise RuntimeError(
            "未安装 Playwright。请在终端执行："
            "pip install playwright && python -m playwright install chromium"
        )

    from playwright.sync_api import sync_playwright

    title = str(payload.get("title", "")).strip()
    content = str(payload.get("content", ""))
    account_id = normalize_account_id(payload.get("account_id"))
    article_id = str(payload.get("article_id", "")).strip()
    if article_id and not re.fullmatch(r"\d+", article_id):
        raise ValueError("无效的 CSDN 草稿文章 ID")
    if not title:
        raise ValueError("文章标题为空")
    if not content.strip():
        raise ValueError("文章正文为空")

    profile_dir = profile_dir_for_account(account_id)
    profile_dir.mkdir(parents=True, exist_ok=True)
    wait_seconds = max(2, min(int(payload.get("auto_save_wait_seconds", 5)), 30))
    warnings: list[str] = []

    with sync_playwright() as playwright:
        context = launch_browser_context(
            playwright,
            profile_dir,
            headless=not bool(payload.get("open_browser", True)),
            viewport={"width": 1440, "height": 1000},
            permissions=["clipboard-read", "clipboard-write"],
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            editor_url = f"{EDITOR_URL}?articleId={article_id}" if article_id else EDITOR_URL
            page.goto(editor_url, wait_until="domcontentloaded", timeout=60000)
            wait_for_login_if_needed(page)
            log(f"sync start account={account_id!r} article_id={article_id or 'new'} title={title!r} url={page.url}")
            fill_title(page, title)
            log("title filled")
            fill_editor(page, content)
            log("markdown filled")

            description = str(payload.get("description", "")).strip()
            if description and not fill_optional(page, [
                'textarea[placeholder*="摘要"]',
                'div.desc-box textarea',
                'textarea',
            ], description):
                warnings.append("未找到摘要输入框")

            # Tags and cover are deliberately best-effort: their widgets vary
            # more often than the title/editor, and missing metadata must not
            # cause a draft to be published or overwrite the body.
            if payload.get("tags"):
                warnings.append("标签已读取但暂未自动选择，需在 CSDN 页面确认")
            if payload.get("cover"):
                warnings.append("封面已读取但暂未自动上传，需在 CSDN 页面确认")

            page.wait_for_timeout(wait_seconds * 1000)
            saved_by_button = click_save_button(page)
            if saved_by_button:
                page.wait_for_timeout(1500)
            saved = bool(saved_by_button or page_has_saved_signal(page))
            if not saved:
                warnings.append("未发现保存按钮或保存成功提示，可能需要在页面手动确认")

            resolved_article_id = extract_article_id(page.url) or article_id

            return {
                "ok": True,
                "saved": saved,
                "save_action": saved_by_button,
                "url": page.url,
                "warnings": warnings,
                "account_id": account_id,
                "article_id": resolved_article_id,
                "updated_existing": bool(article_id),
                "profile_dir": str(profile_dir),
            }
        finally:
            context.close()


def _cleanup_editor_session(account_id: str, session: tuple[Any, Any, Any, str] | None = None) -> None:
    with EDITOR_SESSIONS_LOCK:
        current = EDITOR_SESSIONS.get(account_id)
        if session is not None and current is not session:
            return
        removed = EDITOR_SESSIONS.pop(account_id, None)
    if not removed:
        return
    pw_instance, ctx, _, _ = removed
    try:
        ctx.close()
    except Exception:
        pass
    try:
        pw_instance.stop()
    except Exception:
        pass


def _is_editor_session_alive(session: tuple[Any, Any, Any, str]) -> bool:
    _, ctx, page, _ = session
    try:
        return bool(ctx.pages) and not page.is_closed()
    except Exception:
        return False


def open_editor(payload: dict[str, Any]) -> dict[str, Any]:
    if not has_playwright():
        raise RuntimeError("未安装 Playwright，请先安装依赖。")
    from playwright.sync_api import sync_playwright

    title = str(payload.get("title", "")).strip()
    content = str(payload.get("content", ""))
    account_id = normalize_account_id(payload.get("account_id"))
    article_id = str(payload.get("article_id", "")).strip()
    if article_id and not re.fullmatch(r"\d+", article_id):
        raise ValueError("无效的 CSDN 草稿文章 ID")
    if not title:
        raise ValueError("文章标题为空")
    if not content.strip():
        raise ValueError("文章正文为空")

    with EDITOR_SESSIONS_LOCK:
        existing = EDITOR_SESSIONS.get(account_id)
    if existing:
        if _is_editor_session_alive(existing):
            return {
                "ok": True,
                "opened": False,
                "already_open": True,
                "manual_save_required": True,
                "account_id": account_id,
                "article_id": article_id,
                "url": existing[3],
                "message": "该账号的 CSDN 编辑器窗口已经打开，请直接继续编辑。",
            }
        _cleanup_editor_session(account_id, existing)
    profile_dir = profile_dir_for_account(account_id)
    profile_dir.mkdir(parents=True, exist_ok=True)
    playwright = sync_playwright().start()
    context = None
    try:
        context = launch_browser_context(
            playwright,
            profile_dir,
            headless=False,
            viewport={"width": 1440, "height": 1000},
            permissions=["clipboard-read", "clipboard-write"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        editor_url = f"{EDITOR_URL}?articleId={article_id}" if article_id else EDITOR_URL
        page.goto(editor_url, wait_until="domcontentloaded", timeout=60000)
        wait_for_login_if_needed(page)
        fill_title(page, title)
        fill_editor(page, content)

        warnings: list[str] = []
        description = str(payload.get("description", "")).strip()
        if description and not fill_optional(page, [
            'textarea[placeholder*="摘要"]',
            'div.desc-box textarea',
            'textarea',
        ], description):
            warnings.append("未找到摘要输入框")
        if payload.get("tags"):
            warnings.append("标签已读取但暂未自动选择，需在 CSDN 页面确认")
        if payload.get("cover"):
            warnings.append("封面已读取但暂未自动上传，需在 CSDN 页面确认")

        session_tuple = (playwright, context, page, page.url)
        with EDITOR_SESSIONS_LOCK:
            EDITOR_SESSIONS[account_id] = session_tuple

        def _on_close(*_args: Any) -> None:
            threading.Thread(
                target=_cleanup_editor_session,
                args=(account_id, session_tuple),
                daemon=True,
            ).start()

        context.on("close", _on_close)
        log(f"editor opened account={account_id!r} article_id={article_id or 'new'} title={title!r} url={page.url}")
        return {
            "ok": True,
            "opened": True,
            "manual_save_required": True,
            "account_id": account_id,
            "article_id": extract_article_id(page.url) or article_id,
            "url": page.url,
            "warnings": warnings,
            "profile_dir": str(profile_dir),
        }
    except Exception:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        try:
            playwright.stop()
        except Exception:
            pass
        raise


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "CSDNDraftBridge/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[bridge] {format % args}")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "app://obsidian.md")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        request_url = urlparse(self.path)
        query_map = dict(parse_query(request_url.query))
        self._request_lang = normalize_lang(query_map.get("lang"))
        if request_url.path == "/health":
            json_response(self, 200, {
                "ok": True,
                "bridge_api_version": BRIDGE_API_VERSION,
                "account_profiles": True,
                "qr_login": True,
                "i18n": True,
                "playwright": has_playwright(),
                "profile_dir": str(PROFILE_DIR),
            })
            return
        if request_url.path == "/login/qr/status":
            try:
                query = dict(parse_query(request_url.query))
                account_id = normalize_account_id(query.get("account_id"))
                json_response(self, 200, {"ok": True, **qr_session_snapshot(account_id)})
            except Exception as error:
                json_response(self, 400, {"ok": False, "error": str(error)})
            return
        if request_url.path == "/session":
            try:
                query = dict(parse_query(request_url.query))
                account_id = normalize_account_id(query.get("account_id"))
                verify = str(query.get("verify", "")).lower() in ("1", "true", "yes")
                state = verify_account_session(account_id) if verify else account_state(account_id)
                json_response(self, 200, {"ok": True, **state})
            except Exception as error:
                json_response(self, 400, {"ok": False, "error": str(error)})
            return
        if request_url.path == "/drafts":
            try:
                query = dict(parse_query(request_url.query))
                result = read_drafts({
                    "account_id": query.get("account_id"),
                    "page": query.get("page", "1"),
                    "page_size": query.get("page_size", "20"),
                    "keyword": query.get("keyword", ""),
                    "headless": query.get("headless", "true"),
                })
                json_response(self, 200, result)
            except Exception as error:
                log(f"draft list error: {error}\n{traceback.format_exc()}")
                json_response(self, 500, {"ok": False, "error": str(error)})
            return
        if request_url.path == "/draft":
            try:
                query = dict(parse_query(request_url.query))
                result = read_draft({
                    "account_id": query.get("account_id"),
                    "article_id": query.get("article_id"),
                })
                json_response(self, 200, result)
            except Exception as error:
                log(f"draft read error: {error}\n{traceback.format_exc()}")
                json_response(self, 500, {"ok": False, "error": str(error)})
            return
        if request_url.path == "/login":
            try:
                account_id = normalize_account_id(dict(parse_query(request_url.query)).get("account_id"))
                state = account_state(account_id)
                if state["status"] == "logging_in":
                    json_response(self, 200, {"ok": True, "status": "already-running", "account_id": account_id})
                    return
                if not has_playwright():
                    json_response(self, 500, {"ok": False, "error": "未安装 Playwright，请先安装依赖。"})
                    return
                set_account_state(account_id, "logging_in", "登录窗口运行中，请在浏览器中完成 CSDN 登录")
                threading.Thread(target=login_to_csdn, args=(account_id,), daemon=True).start()
                json_response(self, 202, {"ok": True, "status": "started", "account_id": account_id})
            except Exception as error:
                json_response(self, 400, {"ok": False, "error": str(error)})
            return
        json_response(self, 404, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        request_url = urlparse(self.path)
        query_map = dict(parse_query(request_url.query))
        self._request_lang = normalize_lang(query_map.get("lang"))
        if request_url.path == "/login/qr/start":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                if "lang" in payload:
                    self._request_lang = normalize_lang(payload.get("lang"))
                result = start_qr_login(
                    payload.get("account_id"),
                    payload.get("mode", "wechat"),
                    force_relogin=bool(payload.get("force_relogin", False)),
                )
                json_response(self, 200, {"ok": True, **result})
            except Exception as error:
                log(f"qr start error: {error}\n{traceback.format_exc()}")
                json_response(self, 500, {"ok": False, "error": str(error)})
            return
        if request_url.path == "/login/qr/refresh":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                if "lang" in payload:
                    self._request_lang = normalize_lang(payload.get("lang"))
                result = refresh_qr_login(
                    payload.get("account_id"),
                    payload.get("mode"),
                )
                json_response(self, 200, {"ok": True, **result})
            except Exception as error:
                log(f"qr refresh error: {error}\n{traceback.format_exc()}")
                json_response(self, 500, {"ok": False, "error": str(error)})
            return
        if request_url.path == "/login/qr/cancel":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                if "lang" in payload:
                    self._request_lang = normalize_lang(payload.get("lang"))
                result = cancel_qr_login(payload.get("account_id"))
                json_response(self, 200, {"ok": True, **result})
            except Exception as error:
                json_response(self, 400, {"ok": False, "error": str(error)})
            return
        if request_url.path == "/logout":
            try:
                account_id = normalize_account_id(query_map.get("account_id"))
                profile_dir = profile_dir_for_account(account_id)
                if profile_dir.exists():
                    shutil.rmtree(profile_dir)
                set_account_state(account_id, "unknown", "登录态已清除")
                json_response(self, 200, {"ok": True, "status": "cleared", "account_id": account_id})
            except Exception as error:
                json_response(self, 500, {"ok": False, "error": str(error)})
            return
        if request_url.path == "/drafts/delete":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if "lang" in payload:
                    self._request_lang = normalize_lang(payload.get("lang"))
                result = delete_draft(payload)
                json_response(self, 200, result)
            except Exception as error:
                log(f"draft delete error: {error}\n{traceback.format_exc()}")
                json_response(self, 500, {"ok": False, "error": str(error)})
            return
        if request_url.path == "/open-editor":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if "lang" in payload:
                    self._request_lang = normalize_lang(payload.get("lang"))
                result = open_editor(payload)
                json_response(self, 200, result)
            except Exception as error:
                log(f"open editor error: {error}\n{traceback.format_exc()}")
                json_response(self, 500, {"ok": False, "error": str(error)})
            return
        if request_url.path != "/sync":
            json_response(self, 404, {"ok": False, "error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if "lang" in payload:
                self._request_lang = normalize_lang(payload.get("lang"))
            if not SYNC_LOCK.acquire(blocking=False):
                json_response(self, 409, {"ok": False, "error": "已有同步任务正在运行，请稍后再试"})
                return
            try:
                result = sync_to_csdn(payload)
            finally:
                SYNC_LOCK.release()
            json_response(self, 200, result)
        except Exception as error:
            log(f"sync error: {error}\n{traceback.format_exc()}")
            json_response(self, 500, {"ok": False, "error": str(error)})


def parse_query(query: str) -> list[tuple[str, str]]:
    from urllib.parse import parse_qsl
    return parse_qsl(query, keep_blank_values=True)


def normalize_qr_mode(mode: str | None) -> str:
    value = str(mode or "wechat").strip().lower()
    return "app" if value == "app" else "wechat"


def qr_session_snapshot(account_id: str | None) -> dict[str, Any]:
    normalized = normalize_account_id(account_id)
    with QR_SESSIONS_LOCK:
        entry = QR_SESSIONS.get(normalized)
        if not entry:
            return {
                "account_id": normalized,
                "mode": "wechat",
                "status": "idle",
                "qr_data_url": "",
                "message": "尚未启动扫码登录",
                "updated_at": None,
            }
        return dict(entry["state"])


def _update_qr_state(
    entry: dict[str, Any],
    *,
    status: str | None = None,
    mode: str | None = None,
    qr_data_url: str | None = None,
    message: str | None = None,
) -> None:
    with QR_SESSIONS_LOCK:
        state = entry["state"]
        if status is not None:
            state["status"] = status
        if mode is not None:
            state["mode"] = mode
        if qr_data_url is not None:
            state["qr_data_url"] = qr_data_url
        if message is not None:
            state["message"] = message
        state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")


def _extract_qr_data_url(page: Any, mode: str) -> str:
    selectors = (
        [".app-code-wrap img", 'img[src^="data:image/png;base64,"]']
        if mode == "app"
        else [".public-code img", 'img[src^="data:image/jpeg;base64,"]']
    )
    selectors.append('img[src^="data:image/"]')

    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = locator.count()
        except Exception:
            continue
        for idx in range(count):
            img = locator.nth(idx)
            try:
                if not img.is_visible():
                    continue
                box = img.bounding_box()
                if not box or box["width"] < 100 or box["height"] < 100:
                    continue
                src = (img.get_attribute("src") or "").strip()
                if src.startswith("data:image/") and len(src) > 256:
                    return src
                png_bytes = img.screenshot(type="png")
                if png_bytes:
                    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
            except Exception:
                continue
    return ""


def _switch_qr_tab(page: Any, mode: str) -> None:
    tab_text = "APP登录" if mode == "app" else "微信登录"
    tab = page.get_by_text(tab_text, exact=True).first
    try:
        if tab.count() and tab.is_visible():
            tab.click()
            page.wait_for_timeout(1200)
    except Exception:
        pass


def _is_logged_in_url(url: str) -> bool:
    lower = (url or "").lower()
    if not lower or lower.startswith("chrome-error://") or lower.startswith("about:"):
        return False
    if "passport.csdn.net" in lower or "/login" in lower:
        return False
    return "csdn.net" in lower


def _has_editor_controls(page: Any) -> bool:
    try:
        return page.locator(
            '.article-bar__title-display, input.article-bar__title, .editor__inner[contenteditable="true"]'
        ).count() > 0
    except Exception:
        return False


def _qr_login_worker(account_id: str, entry: dict[str, Any]) -> None:
    from playwright.sync_api import sync_playwright

    cancel_event: threading.Event = entry["cancel_event"]
    refresh_event: threading.Event = entry["refresh_event"]
    profile_dir = profile_dir_for_account(account_id)
    profile_dir.mkdir(parents=True, exist_ok=True)
    set_account_state(account_id, "logging_in", "二维码登录进行中")

    try:
        with sync_playwright() as playwright:
            context = launch_browser_context(
                playwright,
                profile_dir,
                headless=True,
                viewport={"width": 1280, "height": 900},
                permissions=["clipboard-read", "clipboard-write"],
            )
            try:
                if entry.get("force_relogin"):
                    context.clear_cookies()
                    entry["force_relogin"] = False
                else:
                    existing_user = auth_cookie_username(context)
                    if existing_user:
                        _update_qr_state(
                            entry,
                            status="already_logged_in",
                            qr_data_url="",
                            message=f"当前已登录 CSDN 账号：{existing_user}。如需切换账号或重新扫码，请点击“重新扫码”。",
                        )
                        set_account_state(account_id, "logged_in", f"已登录（{existing_user}）")
                        return

                page = context.pages[0] if context.pages else context.new_page()

                def load_qr(mode: str, force_reload: bool = False) -> bool:
                    _update_qr_state(
                        entry,
                        status="loading",
                        mode=mode,
                        qr_data_url="",
                        message="正在获取 CSDN 二维码…",
                    )
                    if entry.get("force_relogin"):
                        context.clear_cookies()
                        entry["force_relogin"] = False
                        force_reload = True
                    if force_reload or "passport.csdn.net" not in (page.url or "").lower():
                        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(2000)

                    if has_auth_cookies(context) and _is_logged_in_url(page.url):
                        return True

                    _switch_qr_tab(page, mode)
                    qr_url = ""
                    for _ in range(15):
                        if cancel_event.is_set():
                            return False
                        if has_auth_cookies(context) and _is_logged_in_url(page.url):
                            return True
                        qr_url = _extract_qr_data_url(page, mode)
                        if qr_url:
                            break
                        page.wait_for_timeout(500)

                    if not qr_url:
                        raise RuntimeError("未能从 CSDN 登录页提取到二维码，请点击刷新或改用浏览器窗口登录。")

                    tip = "请使用 CSDN APP 扫一扫登录" if mode == "app" else "请使用微信扫一扫登录"
                    _update_qr_state(entry, status="ready", mode=mode, qr_data_url=qr_url, message=tip)
                    return False

                already_logged_in = load_qr(entry["desired_mode"], force_reload=True)
                deadline = time.monotonic() + 180.0

                while not already_logged_in:
                    if cancel_event.is_set():
                        _update_qr_state(entry, status="cancelled", message="已取消扫码登录")
                        set_account_state(account_id, "unknown", "已取消扫码登录")
                        return

                    if time.monotonic() >= deadline:
                        _update_qr_state(entry, status="expired", message="扫码登录已超时，请点击刷新重试")
                        return

                    if refresh_event.is_set():
                        refresh_event.clear()
                        target_mode = entry["desired_mode"]
                        force_reload = bool(entry.get("force_reload", False))
                        entry["force_reload"] = False
                        already_logged_in = load_qr(target_mode, force_reload=force_reload)
                        deadline = time.monotonic() + 180.0
                        continue

                    if has_auth_cookies(context):
                        already_logged_in = True
                        break

                    try:
                        body_text = page.locator("body").inner_text(timeout=1500)
                    except Exception:
                        body_text = ""

                    if re.search(r"扫码成功|请在手机|确认登录", body_text):
                        _update_qr_state(entry, status="scanned", message="已扫码，请在手机上点击确认登录…")
                    elif re.search(r"绑定手机|安全验证|滑块", body_text):
                        _update_qr_state(
                            entry,
                            status="error",
                            message="CSDN 要求补充手机号绑定或安全验证，请点击“改用浏览器登录”完成首次验证。",
                        )
                        return
                    elif re.search(r"二维码已失效|二维码已过期|已过期", body_text):
                        _update_qr_state(entry, status="expired", message="二维码已过期，请点击“刷新二维码”")
                    else:
                        latest_qr = _extract_qr_data_url(page, entry["desired_mode"])
                        if latest_qr and latest_qr != entry["state"].get("qr_data_url"):
                            tip = (
                                "请使用 CSDN APP 扫一扫登录"
                                if entry["desired_mode"] == "app"
                                else "请使用微信扫一扫登录"
                            )
                            _update_qr_state(entry, status="ready", qr_data_url=latest_qr, message=tip)

                    page.wait_for_timeout(800)

                # Wait for SSO redirect and cookie persistence on mp.csdn.net
                _update_qr_state(entry, status="scanned", message="登录成功，正在同步草稿箱会话…")
                page.wait_for_timeout(1500)
                if "mp.csdn.net" not in (page.url or "").lower():
                    page.goto(MANAGE_URL, wait_until="domcontentloaded", timeout=30000)
                wait_for_manage_page(page, headless=True)
                page.wait_for_timeout(1200)
                if has_auth_cookies(context):
                    _update_qr_state(entry, status="logged_in", message="登录成功！已保存该账号登录态")
                    set_account_state(account_id, "logged_in", "已通过扫码完成 CSDN 登录")
                    log(f"qr login complete account={account_id!r} mode={entry['desired_mode']!r}")
                else:
                    raise RuntimeError("扫码已完成，但未检测到 CSDN 认证 Cookie，请重试或改用浏览器登录。")
            finally:
                context.close()
    except Exception as error:
        if not cancel_event.is_set():
            _update_qr_state(entry, status="error", message=str(error))
            set_account_state(account_id, "error", str(error))
            log(f"qr login error account={account_id!r}: {error}\n{traceback.format_exc()}")


def cancel_qr_login(account_id: str | None) -> dict[str, Any]:
    normalized = normalize_account_id(account_id)
    with QR_SESSIONS_LOCK:
        entry = QR_SESSIONS.get(normalized)
        if entry:
            entry["cancel_event"].set()
            entry["state"]["status"] = "cancelled"
            entry["state"]["message"] = "已取消扫码登录"
            entry["state"]["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return qr_session_snapshot(normalized)


def start_qr_login(
    account_id: str | None,
    mode: str | None = "wechat",
    *,
    force_relogin: bool = False,
) -> dict[str, Any]:
    if not has_playwright():
        raise RuntimeError("未安装 Playwright，请先安装依赖。")
    normalized = normalize_account_id(account_id)
    qr_mode = normalize_qr_mode(mode)

    old_thread = None
    with QR_SESSIONS_LOCK:
        old_entry = QR_SESSIONS.get(normalized)
        if old_entry:
            old_entry["cancel_event"].set()
            old_thread = old_entry.get("thread")

    if old_thread and old_thread.is_alive():
        old_thread.join(timeout=3.0)

    entry: dict[str, Any] = {
        "cancel_event": threading.Event(),
        "refresh_event": threading.Event(),
        "desired_mode": qr_mode,
        "force_reload": True,
        "force_relogin": force_relogin,
        "state": {
            "account_id": normalized,
            "mode": qr_mode,
            "status": "loading",
            "qr_data_url": "",
            "message": "正在启动扫码登录…",
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "thread": None,
    }
    thread = threading.Thread(target=_qr_login_worker, args=(normalized, entry), daemon=True)
    entry["thread"] = thread
    with QR_SESSIONS_LOCK:
        QR_SESSIONS[normalized] = entry
    thread.start()
    return qr_session_snapshot(normalized)


def refresh_qr_login(account_id: str | None, mode: str | None = None) -> dict[str, Any]:
    normalized = normalize_account_id(account_id)
    with QR_SESSIONS_LOCK:
        entry = QR_SESSIONS.get(normalized)
        thread = entry.get("thread") if entry else None
        is_running = bool(entry and thread and thread.is_alive() and not entry["cancel_event"].is_set())
        if is_running:
            next_mode = normalize_qr_mode(mode or entry["desired_mode"])
            mode_changed = next_mode != entry["desired_mode"]
            entry["desired_mode"] = next_mode
            entry["force_reload"] = not mode_changed
            entry["state"]["mode"] = next_mode
            entry["state"]["status"] = "loading"
            entry["state"]["qr_data_url"] = ""
            entry["state"]["message"] = "正在切换二维码…" if mode_changed else "正在刷新二维码…"
            entry["state"]["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            entry["refresh_event"].set()
            return dict(entry["state"])
    return start_qr_login(normalized, mode or "wechat", force_relogin=True)


def login_to_csdn(account_id: str) -> None:
    """Open an account-specific persistent browser and wait for user login."""
    try:
        if not has_playwright():
            raise RuntimeError("未安装 Playwright，请先安装依赖。")
        from playwright.sync_api import sync_playwright

        profile_dir = profile_dir_for_account(account_id)
        profile_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            context = launch_browser_context(
                playwright,
                profile_dir,
                headless=False,
                viewport={"width": 1440, "height": 1000},
                permissions=["clipboard-read", "clipboard-write"],
            )
            try:
                if has_auth_cookies(context):
                    context.clear_cookies()
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
                deadline = time.monotonic() + 180.0
                while time.monotonic() < deadline:
                    if page.is_closed():
                        raise RuntimeError("登录窗口已关闭。")
                    if has_auth_cookies(context):
                        break
                    page.wait_for_timeout(800)
                if not has_auth_cookies(context):
                    raise RuntimeError("CSDN 登录未完成或已超时。")
                page.goto(MANAGE_URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1500)
                set_account_state(account_id, "logged_in", f"已登录（{auth_cookie_username(context)}）")
                log(f"login complete account={account_id!r}")
            finally:
                context.close()
    except Exception as error:
        set_account_state(account_id, "error", str(error))
        log(f"login error account={account_id!r}: {error}\n{traceback.format_exc()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Obsidian → CSDN 草稿本地桥接服务")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), BridgeHandler)
    print(f"CSDN draft bridge listening at http://{args.host}:{args.port}")
    print(f"Playwright profile: {PROFILE_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping bridge")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
