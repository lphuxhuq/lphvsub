"""Dịch qua Google AI Studio bằng tự động hóa trình duyệt (Playwright).

Không cần API Key — dùng tài khoản Google đăng nhập qua Chrome profile persistent.
Phương thức dịch thứ 2, hoạt động song song với dịch trực tiếp qua API (phương thức 1).

Port từ VoxCraftRecap ai_movie_review.py — giữ nguyên cách vận hành:
- launch_persistent_context với args tối giản
- URL new_chat (không thêm ?model=)
- permission denied → mở chat mới, thử lại
- internal error → gửi lại trên cùng trang, rồi mở chat mới
- stable_ticks >= 3 + Stop button ẩn → trả kết quả
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from autodub.languages import TargetLang
from autodub.progress import ProgressReporter
from autodub.text.glossary import _DEFAULT_PHONETIC_GLOSSARY
from autodub.text.translate_common import TranslateCheckpoint, TranslateError
from autodub.text.translate_direct import (
    _has_cjk,
    parse_response_segments,
)
from autodub.text.translate_hint import (
    annotate_slots,
    build_translation_prompt,
    context_note,
    context_payload,
    effective_cps,
    ensure_terminal_punct,
    payload_segment,
)
from autodub.utils import setup_logging

logger = setup_logging("autodub.translate_browser")

AI_STUDIO_URL = "https://aistudio.google.com/app/prompts/new_chat"
PROMPT_END_MARKER = "<<<LPHV_TRANSLATE_END_F8A3B1>>>"

CHROME_ANTI_CRASH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-hang-monitor",
    "--disable-ipc-flooding-protection",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-features=Translate,OptimizationHints,MediaRouter",
    "--window-size=1280,800",
]


def _safe_extract_page_text(page) -> str:
    """Trích xuất text từ Google AI Studio an toàn và tối ưu bộ nhớ.
    Tự động lọc bỏ các khối suy nghĩ (Model Thoughts) của Gemini 2.5 Flash để lấy chuẩn phần JSON kết quả."""
    if not page or page.is_closed():
        raise RuntimeError("Cửa sổ Chrome (AI Studio) đã bị đóng.")
    try:
        text = page.evaluate("""() => {
            try {
                // 1. Tìm turn chat model cuối cùng
                const modelTurns = document.querySelectorAll('ms-chat-turn:not(.user-turn), .model-turn, .chat-turn.model, ms-chat-turn:last-child');
                const targetTurn = modelTurns.length > 0 ? modelTurns[modelTurns.length - 1] : document.body;
                
                if (targetTurn) {
                    // Thử tìm các node markdown / code không nằm trong thoughts
                    const mdNodes = targetTurn.querySelectorAll('ms-cmark-node, markdown, .rendered-markdown, pre code, .model-response-text');
                    if (mdNodes && mdNodes.length > 0) {
                        let combined = '';
                        for (const node of mdNodes) {
                            if (!node.closest('ms-thought-chunk, ms-thought-node, .thought-content, .model-thoughts, ms-thought-view, .thoughts-container')) {
                                combined += (node.innerText || node.textContent || '') + '\\n';
                            }
                        }
                        if (combined.trim().length > 0) {
                            return combined.trim();
                        }
                    }

                    // Clone và loại bỏ các phần tử thought
                    try {
                        const clone = targetTurn.cloneNode(true);
                        const thoughtEls = clone.querySelectorAll('ms-thought-chunk, ms-thought-node, .thought-content, .model-thoughts, ms-thought-view, .thoughts-container, [data-thought]');
                        thoughtEls.forEach(el => el.remove());
                        const cleanTxt = clone.innerText || clone.textContent || '';
                        if (cleanTxt.trim().length > 0) {
                            return cleanTxt.trim();
                        }
                    } catch (e) {}

                    const rawTxt = targetTurn.innerText || targetTurn.textContent || '';
                    if (rawTxt.trim().length > 0) {
                        return rawTxt.trim();
                    }
                }
                return document.body ? (document.body.innerText || '') : '';
            } catch (e) {
                return document.body ? (document.body.innerText || '') : '';
            }
        }""")
        return str(text or "")
    except Exception as exc:
        err_lower = str(exc).lower()
        if any(k in err_lower for k in ("target closed", "browser has been closed", "connection closed", "crashed")):
            raise RuntimeError(f"Cửa sổ Chrome (AI Studio) đã bị crash hoặc đóng: {exc}") from exc
        try:
            return page.locator("body").inner_text(timeout=5000)
        except Exception as exc2:
            err2 = str(exc2).lower()
            if any(k in err2 for k in ("target closed", "browser has been closed", "connection closed", "crashed")):
                raise RuntimeError(f"Cửa sổ Chrome (AI Studio) đã bị crash hoặc đóng: {exc2}") from exc2
            return ""


def _get_default_profile_dir() -> str:
    configured = str(os.environ.get("AI_STUDIO_CHROME_PROFILE", "") or "").strip()
    if configured:
        return os.path.abspath(os.path.expandvars(os.path.expanduser(configured)))
    user_data_root = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    return os.path.join(user_data_root, "lphvsub", "ChromeProfile_AIStudio")


def _cookie_db_paths(profile_dir: str) -> list[str]:
    return [
        os.path.join(profile_dir, "Default", "Network", "Cookies"),
        os.path.join(profile_dir, "Default", "Cookies"),
        os.path.join(profile_dir, "Network", "Cookies"),
        os.path.join(profile_dir, "Cookies"),
    ]


def _has_google_session(profile_dir: str) -> bool:
    for path in _cookie_db_paths(profile_dir):
        if os.path.isfile(path):
            return True
    login_data = os.path.join(profile_dir, "Default", "Login Data")
    return os.path.isfile(login_data)


def _count_google_cookies(cookie_db: str) -> int:
    import shutil
    import sqlite3
    import tempfile

    tmp_db = os.path.join(tempfile.gettempdir(), f"ai_studio_check_{os.getpid()}.db")
    try:
        shutil.copy2(cookie_db, tmp_db)
    except Exception:
        return -1
    try:
        conn = sqlite3.connect(tmp_db)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(cookies)")
        cols = {row[1] for row in cur.fetchall()}
        if "host_key" not in cols:
            conn.close()
            return 0
        cur.execute(
            "SELECT COUNT(*) FROM cookies WHERE host_key LIKE '%google%' "
            "OR host_key LIKE '%aistudio%'"
        )
        count = int(cur.fetchone()[0] or 0)
        conn.close()
        return count
    except Exception:
        return -1
    finally:
        try:
            os.remove(tmp_db)
        except OSError:
            pass


def check_login_status(profile_dir: str | None = None, timeout_s: int = 15) -> dict:
    p_dir = profile_dir or _get_default_profile_dir()
    has_cookies = _has_google_session(p_dir)
    result = {
        "logged_in": False,
        "profile_dir": p_dir,
        "has_cookies": has_cookies,
        "error": "",
    }
    if not has_cookies:
        result["error"] = "Chưa đăng nhập — chưa có cookies trong Chrome profile."
        _save_login_status(False)
        return result
    cookie_db = next((p for p in _cookie_db_paths(p_dir) if os.path.isfile(p)), "")
    if cookie_db:
        count = _count_google_cookies(cookie_db)
        if count > 0:
            result["logged_in"] = True
            _save_login_status(True)
            return result
        if count == 0:
            result["error"] = "Cookies Google không còn — session đã hết hạn."
            _save_login_status(False)
            return result
    result["logged_in"] = True
    _save_login_status(True)
    return result


def _save_login_status(logged_in: bool) -> None:
    try:
        from autodub_gui.env_store import read_env, write_env
        env = read_env()
        new_val = "true" if logged_in else "false"
        if env.get("AI_STUDIO_LOGGED_IN") != new_val:
            write_env({"AI_STUDIO_LOGGED_IN": new_val})
    except Exception:
        pass


def get_cached_login_status() -> str:
    try:
        from autodub_gui.env_store import read_env
        return read_env().get("AI_STUDIO_LOGGED_IN", "")
    except Exception:
        return ""


class AiStudioBrowserClient:
    """Quản lý phiên Playwright tự động hóa Google AI Studio.

    Vận hành an toàn và tối ưu:
    - launch_persistent_context với bộ cờ chống crash
    - Chạy off-screen window (--window-position=-32000,-32000) khi ẩn thay vì headless=True
      để tránh Google bot detection và tránh lỗi WebGL
    - permission denied → mở chat mới, thử lại
    - internal error / crash → tự động dọn dẹp và khởi chạy lại context sạch sẽ
    """

    def __init__(
        self,
        profile_dir: str | None = None,
        headless: bool = False,
        hide_window: bool = True,
    ):
        self.profile_dir = profile_dir or _get_default_profile_dir()
        os.makedirs(self.profile_dir, exist_ok=True)
        # Luôn dùng headless=False + off-screen window để Google nhận diện là browser thật
        self.hide_window = hide_window or headless
        self._playwright = None
        self._browser_context = None
        self._page = None

    def _ensure_playwright(self):
        if self._playwright is not None and self._browser_context is not None and not self._page.is_closed():
            return
        if self._playwright is None:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
        if self._browser_context is None:
            args = list(CHROME_ANTI_CRASH_ARGS)
            if self.hide_window:
                args.append("--window-position=-32000,-32000")
            else:
                args.append("--window-position=80,80")
            self._browser_context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                headless=False,
                args=args,
            )
        if self._page is None or self._page.is_closed():
            self._page = (
                self._browser_context.pages[0]
                if self._browser_context.pages
                else self._browser_context.new_page()
            )

    def open_login_window(self) -> None:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            headless=False,
            args=list(CHROME_ANTI_CRASH_ARGS) + ["--window-size=1100,850"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        logger.info("Đang mở Google AI Studio để đăng nhập...")
        try:
            page.goto(AI_STUDIO_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            try:
                page.goto(AI_STUDIO_URL, wait_until="commit", timeout=60000)
            except Exception:
                pass
        logger.info(
            "Đã mở cửa sổ đăng nhập — hãy đăng nhập Google, "
            "chọn model Flash miễn phí (2.5 Flash / 2.0 Flash / 1.5 Flash), "
            "rồi đóng cửa sổ Chrome."
        )
        try:
            while True:
                try:
                    if not ctx.pages or all(p.is_closed() for p in ctx.pages):
                        break
                except Exception:
                    break
                time.sleep(0.3)
        finally:
            try:
                ctx.close()
            except Exception:
                pass
            try:
                pw.stop()
            except Exception:
                pass
            if _has_google_session(self.profile_dir):
                _save_login_status(True)

    def _open_fresh_chat(self) -> None:
        self._ensure_playwright()
        fresh = self._browser_context.new_page()
        try:
            fresh.goto(AI_STUDIO_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            try:
                fresh.close()
            except Exception:
                pass
            raise
        try:
            if not self._page.is_closed():
                self._page.close()
        except Exception:
            pass
        self._page = fresh

    def _wait_login(self, timeout_s: int = 120) -> None:
        if "accounts.google.com" not in self._page.url and "signin" not in self._page.url:
            return
        logger.info("Chờ đăng nhập Google AI Studio (tối đa %ds)...", timeout_s)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self._page.is_closed():
                raise RuntimeError("Cửa sổ Chrome đã bị đóng trong lúc chờ đăng nhập.")
            if "aistudio.google.com" in self._page.url and "signin" not in self._page.url:
                logger.info("Đã đăng nhập — đang chuyển tới AI Studio...")
                self._page.goto(AI_STUDIO_URL, wait_until="domcontentloaded", timeout=60000)
                return
            time.sleep(2)
        raise RuntimeError("Hết thời gian chờ đăng nhập Google AI Studio.")

    _EDITOR_SELECTORS = [
        'textarea[aria-label="Enter a prompt"]',
        'textarea[placeholder*="Start typing"]',
        'textarea[placeholder*="Prompt"]',
        "textarea",
        'div[contenteditable="true"]',
        "p-prompt-input textarea",
        ".prompt-input textarea",
    ]

    _STOP_SELECTORS = [
        'mat-icon[svgIcon="stop"]',
        'button:has-text("Stop")',
        'button[mat-tooltip*="Stop"]',
        'button[aria-label*="Stop"]',
    ]

    _RUN_SELECTORS = [
        'button:has-text("Run")',
        'button:has-text("Send")',
        'button[aria-label*="Run"]',
        'button[aria-label*="Send"]',
        'button[mat-tooltip*="Run"]',
        'mat-icon[svgIcon="play_arrow"]',
        "button.run-button",
        'button[type="submit"]',
    ]

    def _find_editor(self):
        editor = None
        for sel in self._EDITOR_SELECTORS:
            try:
                loc = self._page.locator(sel).first
                if loc.is_visible(timeout=1000):
                    editor = loc
                    break
            except Exception:
                pass
        if not editor:
            try:
                self._page.wait_for_selector(
                    "textarea, div[contenteditable='true']", timeout=15000
                )
                editor = self._page.locator("textarea, div[contenteditable='true']").first
            except Exception as exc:
                raise RuntimeError(
                    "Không tìm thấy ô nhập prompt AI Studio. "
                    "Hãy kiểm tra profile đã đăng nhập Google."
                ) from exc
        return editor

    def _fill_prompt(self, editor, prompt: str):
        logger.info("Chờ AI Studio ổn định giao diện (3 giây)...")
        time.sleep(3)
        # Re-locate editor sau khi chờ vì DOM có thể refresh
        editor = self._page.locator(
            'textarea[aria-label="Enter a prompt"], '
            'textarea[placeholder*="Start typing"], '
            "textarea, div[contenteditable='true']"
        ).first
        editor.focus()
        logger.info("Đang điền prompt (%s ký tự)...", f"{len(prompt):,}")

        tag_name = editor.evaluate("el => el.tagName.toLowerCase()")

        # Method 1: JavaScript native setter
        filled = False
        try:
            self._page.evaluate(
                """({editor, text}) => {
                    if (editor.tagName.toLowerCase() === 'textarea') {
                        const nativeSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLTextAreaElement.prototype, 'value').set;
                        nativeSetter.call(editor, text);
                        editor.dispatchEvent(new Event('input', { bubbles: true }));
                        editor.dispatchEvent(new Event('change', { bubbles: true }));
                    } else {
                        editor.innerText = text;
                        editor.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }""",
                {"editor": editor.element_handle(), "text": prompt},
            )
            time.sleep(0.5)
            val = editor.evaluate("el => el.value || el.innerText || ''")
            if len(val.strip()) >= int(len(prompt) * 0.9):
                filled = True
        except Exception:
            pass

        # Method 2: Playwright fill or keyboard chunked insert
        if not filled:
            try:
                if tag_name == "textarea":
                    editor.fill(prompt, timeout=60000)
                    filled = True
                else:
                    editor.focus()
                    self._page.keyboard.press("Control+A")
                    self._page.keyboard.press("Backspace")
                    block_size = 10000
                    for offset in range(0, len(prompt), block_size):
                        self._page.keyboard.insert_text(
                            prompt[offset : offset + block_size]
                        )
                        time.sleep(0.05)
                    filled = True
            except Exception:
                logger.warning("Playwright fill lỗi, chuyển sang clipboard paste...")

        # Method 3: Clipboard paste
        time.sleep(0.5)
        entered = editor.evaluate("el => el.value || el.innerText || ''")
        if len(entered.strip()) < int(len(prompt) * 0.9):
            try:
                self._page.evaluate(
                    "text => navigator.clipboard.writeText(text)", prompt
                )
                editor.focus()
                self._page.keyboard.press("Control+A")
                self._page.keyboard.press("Control+V")
                time.sleep(1.0)
                entered = editor.evaluate("el => el.value || el.innerText || ''")
            except Exception:
                pass

        if len(entered.strip()) < int(len(prompt) * 0.8):
            raise RuntimeError(
                f"Ô nhập AI Studio không khớp prompt ({len(entered.strip())}/{len(prompt)} ký tự)."
            )

        logger.info("Đã điền đủ %s ký tự. Đang kích hoạt gửi prompt...", f"{len(entered.strip()):,}")
        return editor

    def _submit_prompt(self, prompt: str) -> None:
        self._ensure_playwright()
        if "aistudio.google.com" not in self._page.url or "about:blank" in self._page.url:
            logger.info("Đang mở Google AI Studio...")
            self._page.goto(AI_STUDIO_URL, wait_until="domcontentloaded", timeout=60000)
        self._wait_login()

        editor = self._find_editor()
        editor = self._fill_prompt(editor, prompt)

        # Gửi prompt
        editor.focus()
        time.sleep(0.3)
        self._page.keyboard.press("Control+Enter")
        time.sleep(0.8)

        # Kiểm tra AI đã bắt đầu chưa
        started = False
        try:
            current_text = editor.evaluate("el => el.value || el.innerText || ''")
            started = not current_text.strip()
        except Exception:
            started = True

        if not started:
            for sel in self._STOP_SELECTORS:
                try:
                    if self._page.locator(sel).first.is_visible():
                        started = True
                        break
                except Exception:
                    pass

        if not started:
            for btn_sel in self._RUN_SELECTORS:
                try:
                    btn = self._page.locator(btn_sel).first
                    if btn.is_visible():
                        btn.click()
                        break
                except Exception:
                    pass

        for tick in range(30):
            time.sleep(0.5)
            for sel in self._STOP_SELECTORS:
                try:
                    if self._page.locator(sel).first.is_visible():
                        started = True
                        break
                except Exception:
                    pass
            if started:
                break
            try:
                val = editor.evaluate("el => el.value || el.innerText || ''")
                if not val.strip():
                    started = True
                    break
            except Exception:
                started = True
                break
            if tick == 6 and not started:
                editor.focus()
                self._page.keyboard.press("Control+Enter")

        if not started:
            raise RuntimeError("AI Studio không bắt đầu chạy sau khi gửi prompt.")

        logger.info("AI Studio đang xử lý prompt...")

    def _is_generating(self) -> bool:
        for sel in self._STOP_SELECTORS:
            try:
                if self._page.locator(sel).first.is_visible():
                    return True
            except Exception:
                pass
        return False

    def _extract_response_text(self, full_text: str, prompt: str) -> str:
        if not full_text:
            return ""
        clean_prompt = (prompt or "").strip()
        anchors = [
            PROMPT_END_MARKER,
            clean_prompt,
            clean_prompt[-1000:] if len(clean_prompt) >= 1000 else "",
            clean_prompt[-500:] if len(clean_prompt) >= 500 else "",
            clean_prompt[-200:] if len(clean_prompt) >= 200 else "",
            clean_prompt[-100:] if len(clean_prompt) >= 100 else "",
        ]
        for anchor in anchors:
            if anchor and anchor in full_text:
                return full_text.rsplit(anchor, 1)[-1].strip()
        return full_text.strip()

    def _check_error(self, response_text: str) -> str | None:
        lower = response_text.lower()
        if (
            "rate limit" in lower
            or "rate_limit" in lower
            or "resource exhausted" in lower
            or "quota exceeded" in lower
            or "try again later" in lower
        ):
            return "rate_limit"
        if "prohibited content" in lower:
            return "prohibited"

        has_internal_error = False
        try:
            err_banner = self._page.locator(
                "mat-error, .error-banner, div[role='alert']"
            ).first
            if err_banner.is_visible(timeout=100):
                err_txt = err_banner.inner_text().lower()
                if "rate limit" in err_txt or "quota" in err_txt:
                    return "rate_limit"
                if "internal error" in err_txt:
                    has_internal_error = True
                if "permission" in err_txt or "denied" in err_txt:
                    return "permission_denied"
        except Exception:
            pass
        if (
            not has_internal_error
            and len(response_text) < 300
            and "an internal error has occurred" in lower
        ):
            has_internal_error = True
        if has_internal_error:
            return "internal_error"
        if "permission denied" in lower or "failed to generate" in lower:
            return "permission_denied"
        return None

    def translate_batch(self, system_prompt: str, user_prompt: str,
                        max_wait_secs: int = 600, max_retries: int = 3) -> str:
        full_prompt = f"{system_prompt}\n\n{user_prompt}\n\n{PROMPT_END_MARKER}"

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info("  ↻ Thử lại lần %d/%d — khởi động lại AI Studio...", attempt + 1, max_retries)
                    if self._browser_context is None or self._page is None or self._page.is_closed():
                        self.close()
                        self._ensure_playwright()
                    else:
                        self._open_fresh_chat()
                self._submit_prompt(full_prompt)

                started_at = time.time()
                stable_ticks = 0
                last_response_len = -1

                while (time.time() - started_at) < max_wait_secs:
                    time.sleep(2)
                    if self._page.is_closed():
                        raise RuntimeError("Cửa sổ AI Studio đã bị đóng trong lúc chờ kết quả.")

                    full_text = _safe_extract_page_text(self._page)
                    if not full_text:
                        continue

                    lower_text = full_text.lower()

                    # Check permission denied / rate limit trên toàn bộ page
                    if "permission denied" in lower_text or "failed to generate" in lower_text:
                        logger.warning("  ⚠ AI Studio báo permission denied — mở chat mới...")
                        break
                    if "rate limit" in lower_text or "reached your rate limit" in lower_text:
                        logger.warning("  ⚠ AI Studio báo Rate Limit (quá tải) — chờ 15s rồi thử lại...")
                        time.sleep(15)
                        break

                    response_text = self._extract_response_text(full_text, full_prompt) or ""

                    err = self._check_error(response_text)
                    if err == "internal_error":
                        logger.warning("  ⚠ AI Studio báo lỗi nội bộ — thử gửi lại...")
                        time.sleep(3)
                        try:
                            self._submit_prompt(full_prompt)
                        except Exception:
                            pass
                        started_at = time.time()
                        stable_ticks = 0
                        last_response_len = -1
                        continue
                    if err == "permission_denied":
                        logger.warning("  ⚠ AI Studio báo permission denied — mở chat mới...")
                        break
                    if err == "rate_limit":
                        logger.warning("  ⚠ AI Studio báo Rate Limit (quá tải) — chờ 15s rồi thử lại...")
                        time.sleep(15)
                        break
                    if err == "prohibited":
                        raise TranslateError(
                            "Nội dung bị bộ lọc an toàn của AI Studio chặn."
                        )

                    if response_text and len(response_text) > 30:
                        current_len = len(response_text)
                        if current_len == last_response_len:
                            stable_ticks += 1
                        else:
                            stable_ticks = 0
                        last_response_len = current_len

                        has_json = ("[" in response_text and "{" in response_text) or '{"segments"' in response_text or "```" in response_text
                        is_closed_json = ("]" in response_text or "}" in response_text)

                        # Nếu đã có cấu trúc JSON hợp lệ và không còn generating hoặc ổn định:
                        if has_json:
                            if (not self._is_generating() and is_closed_json) or stable_ticks >= 2:
                                return response_text
                        else:
                            # Chưa có JSON (có thể model đang suy nghĩ) -> chờ ít nhất 5 nhịp (10s) ổn định
                            if not self._is_generating() and stable_ticks >= 5:
                                return response_text

            except Exception as e:
                logger.warning("  ✗ Lỗi trong lúc xử lý AI Studio (lần %d/%d): %s", attempt + 1, max_retries, e)
                # Tự dọn dẹp browser nếu bị crash để lượt sau khởi tạo lại sạch sẽ
                if "crash" in str(e).lower() or "closed" in str(e).lower() or (self._page and self._page.is_closed()):
                    self.close()
                if attempt + 1 >= max_retries:
                    raise
                time.sleep(3)
                continue

        raise TranslateError(
            "Google AI Studio liên tục báo lỗi sau "
            f"{max_retries} lần thử. Hãy mở AI Studio, chọn model "
            "Flash miễn phí (2.5 Flash / 2.0 Flash / 1.5 Flash), rồi chạy lại."
        )

    def close(self) -> None:
        if self._browser_context:
            try:
                self._browser_context.close()
            except Exception:
                pass
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._browser_context = None
        self._playwright = None
        self._page = None






def _phonetic_glossary_lines() -> str:
    lines = [
        "### FIXED PHONETIC / INFORMAL SPELLINGS (MANDATORY)",
        "Khi gặp các từ/ngữ sau trong câu, dùng phiên âm/ngữ âm bên phải (viết cho TTS đọc):",
    ]
    for src, dst in _DEFAULT_PHONETIC_GLOSSARY:
        lines.append(f'  "{src}" → "{dst}"')
    return "\n".join(lines)


def _build_single_user_prompt(
    segments: List[dict],
    target: TargetLang,
    cps: float,
    context_segs: List[dict],
) -> str:
    payload_items = [payload_segment(s, cps_budget=cps) for s in segments]
    user_lines = []
    if context_segs:
        user_lines.append(context_note(target))
        user_lines.append(f'"context": {json.dumps(context_segs, ensure_ascii=False)}')
        user_lines.append("")
    user_lines.append(_phonetic_glossary_lines())
    user_lines.append("")
    user_lines.append(
        f"### CRITICAL REQUIREMENT (BẮT BUỘC):\n"
        f"1. Dịch TẤT CẢ {len(segments)} câu thoại sau sang {target.name} ({target.text_field}).\n"
        f"2. BẮT BUỘC trả về ĐÚNG MỘT mảng JSON duy nhất, bắt đầu bằng `[` và kết thúc bằng `]`.\n"
        f"3. TUYỆT ĐỐI KHÔNG giải thích, KHÔNG viết suy nghĩ (thoughts/reasoning), KHÔNG kèm bất kỳ lời dẫn tiếng Anh hay tiếng Việt nào.\n"
        f"Dữ liệu đầu vào ({len(segments)} câu):\n"
        f"{json.dumps(payload_items, ensure_ascii=False)}"
    )
    return "\n".join(user_lines)
def _apply_translated_map(
    batch: List[dict],
    translated_items: List[dict],
    target: TargetLang,
    fallback_text_field: str = "text",
) -> List[dict]:
    trans_map = {
        item["id"]: item[target.text_field]
        for item in translated_items
        if "id" in item and target.text_field in item
    }
    batch_results = []
    for s in batch:
        sid = s["id"]
        txt = trans_map.get(sid, "")
        if not txt:
            txt = s.get(fallback_text_field, "")
        new_seg = dict(s)
        new_seg[target.text_field] = ensure_terminal_punct(txt)
        batch_results.append(new_seg)
    return batch_results


def _build_browser_system_prompt(target: TargetLang, source_lang: str, settings: Any = None) -> str:
    target_field = target.text_field
    domain = getattr(settings, "translate_domain", "general").strip() or "general"

    style_guide = "phong cách review phim/kể chuyện YouTube/TikTok, tự nhiên, cuốn hút"
    if "novel" in domain.lower() or "fiction" in domain.lower():
        style_guide = "phong cách tiểu thuyết, kiếm hiệp, ngôn tình, xưng hô chuẩn bối cảnh"
    elif "anime" in domain.lower():
        style_guide = "phong cách anime, hoạt hình, năng động, trẻ trung"

    return f"""Bạn là chuyên gia chuyển thể lồng tiếng video từ {source_lang} sang {target.name} cho AI TTS.
NGUYÊN TẮC BẮT BUỘC:
1. Độ dài câu: Khống chế độ dài ký tự của bản dịch không vượt quá trường 'max_chars' trong mỗi câu. Câu dịch phải ngắn gọn, súc tích, lược bỏ từ thừa để AI đọc vừa khít thời lượng video gốc.
2. Ngôn ngữ: Dịch sang {target.name} ({style_guide}), xưng hô chuẩn xác theo vai vế, thuần Việt, tự nhiên.
3. Chuyển ngữ toàn bộ: Tên nhân vật, địa danh, thuật ngữ phải được phiên âm hoặc dịch sang tiếng Việt, TUYỆT ĐỐI KHÔNG để lại chữ Hán/Nhật/Hàn.
4. Định dạng đầu ra: BẮT BUỘC trả về DUY NHẤT một mảng JSON các object gồm đúng 2 trường: 'id' (giữ nguyên) và '{target_field}' (câu dịch). Ví dụ:
[
  {{"id": 1, "{target_field}": "Lời dịch câu 1."}},
  {{"id": 2, "{target_field}": "Lời dịch câu 2."}}
]
5. TUYỆT ĐỐI KHÔNG giải thích, KHÔNG viết suy nghĩ (thoughts/reasoning), KHÔNG dùng tiếng Anh, KHÔNG thêm bất kỳ lời dẫn nào."""


def translate_segments_browser(
    segments: List[dict],
    target: TargetLang,
    source_lang: str,
    settings: Any,
    reporter: Optional[ProgressReporter] = None,
    checkpoint_path: Optional[str] = None,
) -> List[dict]:
    """Dịch toàn bộ các câu thoại qua Google AI Studio bằng trình duyệt (Playwright)."""
    annotate_slots(segments)
    cps = effective_cps(settings)
    batch_size = max(1, min(int(getattr(settings, "translate_batch_size", 10) or 10), 15))
    single_chat = getattr(settings, "ai_studio_single_chat", True)

    checkpoint = (
        TranslateCheckpoint(checkpoint_path, text_field=target.text_field)
        if checkpoint_path
        else None
    )

    system_prompt = _build_browser_system_prompt(
        target=target,
        source_lang=source_lang,
        settings=settings,
    )

    headless = getattr(settings, "ai_studio_headless", False)
    profile_dir = getattr(settings, "ai_studio_chrome_profile", "").strip() or None

    logger.info(
        "Bắt đầu dịch qua Google AI Studio (trình duyệt) %d câu — single_chat=%s (headless=%s)...",
        len(segments), single_chat, headless,
    )
    if reporter:
        reporter.emit("translate", "start", detail=f"0/{len(segments)} câu (AI Studio)")

    client = AiStudioBrowserClient(profile_dir=profile_dir, headless=headless)
    translated_segments_map: Dict[int, dict] = {}
    t_trans_start = time.time()

    # Restore checkpoint
    completed_count = 0
    for s in segments:
        cached = checkpoint.take([s]) if checkpoint else None
        if cached:
            translated_segments_map[s["id"]] = cached[0]
            completed_count += 1

    if reporter and completed_count > 0:
        reporter.emit("translate", "progress", detail=f"{completed_count}/{len(segments)} câu")

    try:
        if single_chat:
            # Gửi theo từng chunk an toàn (100 câu/lần) để không vượt giới hạn output token của Gemini
            # và cập nhật tiến độ liên tục lên UI
            pending_segments = [s for s in segments if s["id"] not in translated_segments_map]
            chunk_size = 100
            total_pending = len(pending_segments)
            for idx in range(0, total_pending, chunk_size):
                if reporter:
                    reporter.check_cancelled()
                chunk = pending_segments[idx : idx + chunk_size]
                logger.info(
                    "  ▶ Dịch AI Studio: %d/%d câu (lô #%d..#%d)...",
                    len(translated_segments_map),
                    len(segments),
                    chunk[0]["id"],
                    chunk[-1]["id"],
                )
                start_seg_idx = chunk[0].get("index", idx)
                context_segs = context_payload(segments, start_seg_idx, target=target)
                user_prompt = _build_single_user_prompt(chunk, target, cps, context_segs)

                # Retry loop cho riêng từng chunk nếu AI Studio trả về văn bản hội thoại/lỗi JSON
                translated_items: List[dict] = []
                for try_i in range(3):
                    try:
                        if try_i > 0:
                            logger.info(
                                "  ↻ Thử lại lô #%d..#%d (lần %d/3)...",
                                chunk[0]["id"],
                                chunk[-1]["id"],
                                try_i + 1,
                            )
                        raw_reply = client.translate_batch(system_prompt, user_prompt, max_wait_secs=180)
                        translated_items = parse_response_segments(raw_reply, text_field=target.text_field)
                        if translated_items:
                            break
                    except Exception as e:
                        logger.warning(
                            "  ⚠ Lô #%d..#%d lỗi parse/dịch (lần %d/3): %s",
                            chunk[0]["id"],
                            chunk[-1]["id"],
                            try_i + 1,
                            e,
                        )
                        time.sleep(2)

                batch_results = _apply_translated_map(
                    chunk, translated_items, target, fallback_text_field="text"
                )
                for s in batch_results:
                    translated_segments_map[s["id"]] = s
                if checkpoint:
                    checkpoint.put(batch_results)
                if reporter:
                    reporter.emit(
                        "translate",
                        "progress",
                        detail=f"{len(translated_segments_map)}/{len(segments)} câu",
                    )
        else:
            # Batch mode (legacy)
            batches: List[Tuple[int, List[dict], int]] = []
            for i in range(0, len(segments), batch_size):
                b_idx = (i // batch_size) + 1
                batches.append((b_idx, segments[i : i + batch_size], i))
            total_batches = len(batches)

            for b_idx, batch, start_idx in batches:
                if reporter:
                    reporter.check_cancelled()

                # Skip already translated
                batch = [s for s in batch if s["id"] not in translated_segments_map]
                if not batch:
                    continue

                seg_ids = [s["id"] for s in batch]
                logger.info(
                    "  ▶ Lô %d/%d bắt đầu (%d câu: %s..%s)",
                    b_idx, total_batches, len(batch), seg_ids[0], seg_ids[-1],
                )
                _t0 = time.time()

                payload_items = [payload_segment(s, cps_budget=cps) for s in batch]
                ctx_segs = context_payload(segments, start_idx, target=target)
                user_lines = []
                if ctx_segs:
                    user_lines.append(context_note(target))
                    user_lines.append(f'"context": {json.dumps(ctx_segs, ensure_ascii=False)}')
                    user_lines.append("")
                user_lines.append(_phonetic_glossary_lines())
                user_lines.append("")
                user_lines.append(
                    f"Dịch các câu thoại sau sang {target.name} ({target.text_field}):\n"
                    f"{json.dumps(payload_items, ensure_ascii=False)}"
                )
                user_prompt = "\n".join(user_lines)

                translated_items: List[dict] = []
                last_err = None
                for try_i in range(2):
                    try:
                        raw_reply = client.translate_batch(system_prompt, user_prompt)
                        translated_items = parse_response_segments(
                            raw_reply, text_field=target.text_field
                        )
                        if translated_items:
                            break
                    except TranslateError:
                        raise
                    except Exception as e:
                        last_err = e
                        logger.warning("  ✗ Lô %d lỗi (lần %d): %s", b_idx, try_i + 1, e)

                if not translated_items and last_err:
                    logger.warning("  ⚠ Lô %d lỗi parse — giữ nguyên gốc: %s", b_idx, last_err)

                batch_results = _apply_translated_map(
                    batch, translated_items, target, fallback_text_field="text"
                )
                for s in batch_results:
                    translated_segments_map[s["id"]] = s
                if checkpoint:
                    checkpoint.put(batch_results)

                elapsed = time.time() - _t0
                logger.info(
                    "  ✓ Lô %d/%d hoàn thành — %.1fs",
                    b_idx, total_batches, elapsed,
                )
                if reporter:
                    reporter.emit(
                        "translate", "progress",
                        detail=f"{len(translated_segments_map)}/{len(segments)} câu"
                    )

    finally:
        client.close()

    results = [translated_segments_map.get(s["id"], s) for s in segments]

    # Hậu xử lý CJK (dịch bù theo lô nhanh gọn thay vì từng câu đơn lẻ)
    cjk_untranslated = [s for s in results if _has_cjk(s.get(target.text_field, ""))]
    if cjk_untranslated:
        logger.info(
            "[Hậu xử lý] Phát hiện %d câu còn sót ký tự CJK — đang dịch bù theo lô...",
            len(cjk_untranslated),
        )
        client = AiStudioBrowserClient(profile_dir=profile_dir, headless=headless)
        try:
            cjk_chunk_size = 50
            for c_idx in range(0, len(cjk_untranslated), cjk_chunk_size):
                sub_chunk = cjk_untranslated[c_idx : c_idx + cjk_chunk_size]
                try:
                    payload_items = [payload_segment(s, cps_budget=cps) for s in sub_chunk]
                    re_prompt = (
                        f"### CRITICAL REQUIREMENT (BẮT BUỘC):\n"
                        f"1. Dịch TẤT CẢ {len(sub_chunk)} câu thoại sang {target.name} ({target.text_field}), bắt buộc thoát ý hoàn toàn, không để lại chữ Hán/Nhật/Hàn.\n"
                        f"2. BẮT BUỘC trả về ĐÚNG MỘT mảng JSON duy nhất (bắt đầu bằng `[` và kết thúc bằng `]`).\n"
                        f"3. TUYỆT ĐỐI KHÔNG giải thích, KHÔNG viết suy nghĩ (thoughts/reasoning), KHÔNG kèm bất kỳ lời dẫn tiếng Anh hay tiếng Việt nào.\n"
                        f"Dữ liệu đầu vào ({len(sub_chunk)} câu):\n"
                        f"{json.dumps(payload_items, ensure_ascii=False)}"
                    )
                    re_reply = client.translate_batch(system_prompt, re_prompt, max_wait_secs=120)
                    re_parsed = parse_response_segments(re_reply, text_field=target.text_field)
                    re_map = {
                        item["id"]: item[target.text_field]
                        for item in re_parsed
                        if "id" in item and target.text_field in item
                    }
                    for s in sub_chunk:
                        new_txt = re_map.get(s["id"], "")
                        if new_txt and not _has_cjk(new_txt):
                            s[target.text_field] = ensure_terminal_punct(new_txt)
                            translated_segments_map[s["id"]] = s
                    if checkpoint:
                        checkpoint.put(sub_chunk)
                    logger.info("  ✓ Đã dịch bù xong lô %d câu CJK", len(sub_chunk))
                except Exception as exc:
                    logger.warning("  ✗ Dịch bù lô CJK không thành công: %s", exc)
        finally:
            client.close()

    if checkpoint_path and os.path.exists(checkpoint_path):
        try:
            os.remove(checkpoint_path)
        except OSError:
            pass

    total_elapsed = time.time() - t_trans_start
    if reporter:
        reporter.emit("translate", "done", detail=f"{len(results)} câu")
    logger.info("Dịch AI Studio hoàn tất: %d câu — %.1fs", len(results), total_elapsed)
    return results