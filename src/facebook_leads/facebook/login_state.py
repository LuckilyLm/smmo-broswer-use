from __future__ import annotations

from .models import FacebookLoginState

MAX_LOGIN_STATE_TEXT_CHARS = 5000

CHECKPOINT_URL_MARKERS = ("/checkpoint/", "/help/contact/logout")
CAPTCHA_MARKERS = (
    "captcha",
    "security check",
    "confirm you're not a robot",
    "enter the characters",
    "安全验证",
    "验证码",
)
LOGGED_OUT_MARKERS = (
    "log into facebook",
    "log in to facebook",
    "facebook log in",
    "forgotten password",
    "forgot password",
    "create new account",
    "登录 facebook",
    "登录或注册",
)
LOGGED_IN_MARKERS = (
    "home",
    "watch",
    "marketplace",
    "notifications",
    "messenger",
    "主页",
    "通知",
)


async def detect_login_state(page) -> FacebookLoginState:
    url = (getattr(page, "url", "") or "").lower()
    title = (await _safe_title(page)).lower()
    body_text = (await _safe_limited_body_text(page)).lower()
    combined = f"{url}\n{title}\n{body_text}"

    if any(marker in url for marker in CHECKPOINT_URL_MARKERS):
        return "checkpoint"
    if any(marker in combined for marker in CAPTCHA_MARKERS):
        return "captcha"
    if await _has_login_form(page) or any(marker in combined for marker in LOGGED_OUT_MARKERS):
        return "logged_out"
    if "facebook.com" in url and any(marker in combined for marker in LOGGED_IN_MARKERS):
        return "logged_in"
    if "facebook.com" in url and "login" not in url:
        return "logged_in"
    return "unknown"


async def _safe_title(page) -> str:
    try:
        return await page.title()
    except Exception:
        return ""


async def _safe_limited_body_text(page) -> str:
    try:
        locator = page.locator("body")
        text = await locator.inner_text(timeout=1500)
    except Exception:
        return ""
    return text[:MAX_LOGIN_STATE_TEXT_CHARS]


async def _has_login_form(page) -> bool:
    selectors = [
        "input[name='email']",
        "input[name='pass']",
        "form[action*='login']",
        "[data-testid='royal_login_button']",
    ]
    for selector in selectors:
        try:
            if await page.locator(selector).count() > 0:
                return True
        except Exception:
            continue
    return False

