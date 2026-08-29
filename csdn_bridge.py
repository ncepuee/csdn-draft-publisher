"""Local Playwright bridge for syncing an Obsidian Markdown note to a CSDN draft.

This service deliberately never clicks a button whose accessible name contains
"发布". CSDN's private editor DOM changes over time, so selectors are grouped
as fallbacks and failures are reported instead of silently publishing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


HOST = "127.0.0.1"
PORT = 8765
BRIDGE_API_VERSION = "0.5.0"
EDITOR_URL = "https://editor.csdn.net/md/"
MANAGE_URL = "https://mp.csdn.net/mp_blog/manage/article"
PROFILE_DIR = Path(
    os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
) / "CSDN-Draft-Publisher" / "playwright-profile"
PROFILE_ROOT = PROFILE_DIR.parent / "profiles"
LOG_FILE = PROFILE_DIR.parent / "bridge.log"
SYNC_LOCK = threading.Lock()
ACCOUNT_STATE_LOCK = threading.Lock()
ACCOUNT_STATES: dict[str, dict[str, Any]] = {}
EDITOR_SESSIONS_LOCK = threading.Lock()
EDITOR_SESSIONS: dict[str, tuple[Any, Any, Any, str]] = {}


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


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
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


def wait_for_manage_page(page: Any) -> None:
    try:
        page.wait_for_selector('[role="tab"]', state="visible", timeout=180000)
    except Exception as error:
        if "passport.csdn.net" in page.url or "login" in page.url.lower():
            raise RuntimeError("CSDN 登录未完成或已超时，请先在助手浏览器中完成登录。") from error
        raise RuntimeError("未检测到 CSDN 内容管理页面，请确认已登录。") from error


def wait_for_article_results(page: Any) -> None:
    try:
        page.locator(
            ".article-list-item-mp, .el_mcm-pagination, .no-data-box",
        ).first.wait_for(state="visible", timeout=60000)
    except Exception as error:
        raise RuntimeError("CSDN 内容管理列表加载超时，请稍后重试。") from error


def article_list_response(response: Any, status: str = "draft") -> bool:
    return (
        "/blog/phoenix/console/v1/article/list" in response.url
        and f"status={status}" in response.url
        and response.request.method == "GET"
    )


def extract_article_id(url: str) -> str | None:
    match = re.search(r"[?&]articleId=(\d+)", url or "")
    return match.group(1) if match else None


def manage_page_for_account(playwright: Any, account_id: str) -> tuple[Any, Any]:
    profile_dir = profile_dir_for_account(account_id)
    profile_dir.mkdir(parents=True, exist_ok=True)
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,
        viewport={"width": 1440, "height": 1000},
        permissions=["clipboard-read", "clipboard-write"],
    )
    try:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(MANAGE_URL, wait_until="domcontentloaded", timeout=60000)
        wait_for_manage_page(page)
        return context, page
    except Exception:
        context.close()
        raise


def read_drafts(payload: dict[str, Any]) -> dict[str, Any]:
    if not has_playwright():
        raise RuntimeError("未安装 Playwright，请先安装依赖。")
    from playwright.sync_api import sync_playwright

    account_id = normalize_account_id(payload.get("account_id"))
    page_number = max(1, min(int(payload.get("page", 1)), 1000))
    keyword = str(payload.get("keyword", "")).strip()
    page_size = max(1, min(int(payload.get("page_size", 20)), 50))

    with sync_playwright() as playwright:
        context, page = manage_page_for_account(playwright, account_id)
        try:
            tabs = page.get_by_role("tab")
            if tabs.count() < 5:
                raise RuntimeError("CSDN 内容管理页面未加载完整，无法定位草稿箱。")
            try:
                with page.expect_response(
                    lambda response: article_list_response(response),
                    timeout=60000,
                ):
                    tabs.nth(4).click()
            except Exception as error:
                raise RuntimeError("CSDN 草稿箱接口响应超时，请确认登录态仍然有效。") from error
            wait_for_article_results(page)

            search = page.locator('input[placeholder="请输入标题关键词"]').first
            if keyword and search.count():
                search.fill(keyword)
                try:
                    with page.expect_response(
                        lambda response: article_list_response(response),
                        timeout=60000,
                    ):
                        page.get_by_role("button", name="搜索").click()
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
                            lambda response: article_list_response(response),
                            timeout=60000,
                        ):
                            next_button.click()
                    except Exception as error:
                        raise RuntimeError("CSDN 草稿分页请求超时，请稍后重试。") from error
                    wait_for_article_results(page)

            links = page.locator('a[href*="editor.csdn.net/md/?articleId="]')
            items: list[dict[str, Any]] = []
            seen: set[str] = set()
            for index in range(links.count()):
                link = links.nth(index)
                href = link.get_attribute("href") or ""
                article_id = extract_article_id(href)
                title = (link.inner_text() or "").strip()
                if not article_id or article_id in seen or not title:
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
            if not items and page.locator(".el_mcm-pagination").count() == 0:
                raise RuntimeError("CSDN 草稿列表加载失败，请稍后重试。")
            draft_count = None
            try:
                draft_count_match = re.search(r"\((\d+)\)", tabs.nth(4).inner_text())
                draft_count = int(draft_count_match.group(1)) if draft_count_match else None
            except Exception:
                pass
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
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
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
        context, page = manage_page_for_account(playwright, account_id)
        try:
            page.get_by_role("tab").nth(4).click()
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
            "未安装 Playwright。请在 PowerShell 执行："
            "python -m pip install -r G:\\Obnotes\\tools\\csdn-draft-publisher\\requirements.txt"
            "；然后执行：python -m playwright install chromium"
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
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
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

            return {
                "ok": True,
                "saved": saved,
                "save_action": saved_by_button,
                "url": page.url,
                "warnings": warnings,
                "account_id": account_id,
                "article_id": article_id,
                "updated_existing": bool(article_id),
                "profile_dir": str(profile_dir),
            }
        finally:
            context.close()


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
    profile_dir = profile_dir_for_account(account_id)
    profile_dir.mkdir(parents=True, exist_ok=True)
    playwright = sync_playwright().start()
    context = None
    try:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
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

        with EDITOR_SESSIONS_LOCK:
            EDITOR_SESSIONS[account_id] = (playwright, context, page, page.url)
        log(f"editor opened account={account_id!r} article_id={article_id or 'new'} title={title!r} url={page.url}")
        return {
            "ok": True,
            "opened": True,
            "manual_save_required": True,
            "account_id": account_id,
            "article_id": article_id,
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
        if request_url.path == "/health":
            json_response(self, 200, {
                "ok": True,
                "bridge_api_version": BRIDGE_API_VERSION,
                "account_profiles": True,
                "playwright": has_playwright(),
                "profile_dir": str(PROFILE_DIR),
            })
            return
        if request_url.path == "/session":
            try:
                account_id = normalize_account_id(dict(parse_query(request_url.query)).get("account_id"))
                json_response(self, 200, {"ok": True, **account_state(account_id)})
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
        if request_url.path == "/logout":
            try:
                account_id = normalize_account_id(dict(parse_query(request_url.query)).get("account_id"))
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


def login_to_csdn(account_id: str) -> None:
    """Open an account-specific persistent browser and wait for user login."""
    try:
        if not has_playwright():
            raise RuntimeError("未安装 Playwright，请先安装依赖。")
        from playwright.sync_api import sync_playwright

        profile_dir = profile_dir_for_account(account_id)
        profile_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                viewport={"width": 1440, "height": 1000},
                permissions=["clipboard-read", "clipboard-write"],
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(EDITOR_URL, wait_until="domcontentloaded", timeout=60000)
                wait_for_login_if_needed(page)
                set_account_state(account_id, "logged_in", "已检测到 CSDN Markdown 编辑器")
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
