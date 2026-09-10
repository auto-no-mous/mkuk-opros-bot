"""Optional engine: the same run, but performed by a real browser you can watch.

This exists for checking, not for the machines the bot is deployed to -- those
keep using the dependency-free HTTP engine. Playwright is imported lazily so that
nothing here is needed unless the browser engine is actually selected.

The answering rules are *not* duplicated: each page's HTML is read out of the
browser and handed to the same `SurveyPage` model and the same
`survey_bot.choose_for_question`, so the browser clicks exactly what the HTTP
engine would have posted.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from bot import survey_bot
from bot.page import ORG_GATE_CLASS, SUBMIT_BUTTON_ID, SurveyPage
from bot.survey_bot import BrowserUnavailable

ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = ROOT / "vendor"

# Preference order when `channel` is "auto": browsers already on the machine come
# first, so nothing has to be downloaded. Edge ships with Windows 10/11.
AUTO_CHANNELS = ("msedge", "chrome", None)


def ensure_playwright(log=print) -> None:
    """Imports Playwright, installing it from `vendor/` offline if it is missing."""
    try:
        import playwright.sync_api  # noqa: F401
        return
    except ImportError:
        pass

    wheels = list(VENDOR_DIR.glob("*.whl"))
    if not wheels:
        raise BrowserUnavailable(
            "Браузерный режим требует пакет Playwright, но он не установлен.\n"
            "Положите колёса в папку vendor/ (см. readme, раздел «Браузерный режим») "
            "или установите обычным способом: pip install playwright"
        )

    log(f"Устанавливаю Playwright из папки vendor/ ({len(wheels)} файлов, без интернета)...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-index",
         "--find-links", str(VENDOR_DIR), "playwright"],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        raise BrowserUnavailable(
            "Не удалось установить Playwright из папки vendor/.\n"
            "Скорее всего, колёса собраны под другую версию Python — "
            "перекачайте их через tools/fetch_vendor.py."
        )
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError as exc:
        raise BrowserUnavailable(f"Playwright установился, но не импортируется: {exc}") from exc


def _launch(playwright, config: dict, log):
    browser_config = config.get("browser", {})
    headless = bool(browser_config.get("headless", False))
    channel = browser_config.get("channel", "auto")
    candidates = AUTO_CHANNELS if channel == "auto" else (channel,)

    failures = []
    for candidate in candidates:
        try:
            if candidate is None:
                browser = playwright.chromium.launch(headless=headless)
                log("Запустил Chromium, скачанный Playwright.")
            else:
                browser = playwright.chromium.launch(channel=candidate, headless=headless)
                log(f"Запустил установленный в системе браузер: {candidate}.")
            return browser
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{candidate or 'chromium'}: {str(exc).splitlines()[0]}")

    raise BrowserUnavailable(
        "Не удалось запустить ни один браузер.\n" + "\n".join(failures) + "\n"
        "Установите Microsoft Edge или Google Chrome, либо скачайте браузер "
        "командой: python -m playwright install chromium"
    )


def _click_option(page, option) -> None:
    """Selects a radio option the way a real user would.

    Some answer styles (e.g. the gender buttons) hide the native input behind
    Bootstrap's `.btn-check` (pointer-events: none), so clicking the input itself
    doesn't register -- the visible <label> has to be clicked instead. Other
    styles (matrix table cells) hide the label and only the input is clickable.
    """
    label = page.locator(f"label[for='{option.input_id}']")
    if label.count() > 0 and label.first.is_visible():
        label.first.click(force=True)
    else:
        page.locator(f"#{option.input_id}").check(force=True)


def complete_survey(page, config: dict, on_page=None, on_decision=None) -> bool:
    """Walks one pass of the survey in the browser. Mirrors survey_bot.complete_survey."""
    delays = config["delays"]

    def stopped() -> bool:
        # Read through the module: run() replaces the event object on every start.
        return survey_bot._stop_event.is_set()

    def current() -> SurveyPage:
        survey_page = SurveyPage(page.url, page.content())
        if on_page:
            on_page(survey_page)
        return survey_page

    page.goto(config["survey_url"])
    survey_bot.sleep_range(delays["page_change_seconds"])

    for _ in range(survey_bot.MAX_STEPS):
        if stopped():
            return False
        survey_page = current()
        if survey_page.is_completed:
            return True

        rejected = survey_page.rejected_questions()
        if rejected:
            raise survey_bot.SurveyError("Сайт не принял ответы на вопросы: " + "; ".join(rejected))

        if survey_page.org_gate_url is not None:
            with page.expect_navigation():
                page.click(f".{ORG_GATE_CLASS}")
            survey_bot.sleep_range(delays["page_change_seconds"])
            continue

        if not survey_page.has_form:
            raise survey_bot.SurveyError(
                "На странице опроса нет формы — возможно, сайт вернул что-то неожиданное"
            )

        if not survey_page.is_welcome:
            for question in survey_page.questions():
                chosen = survey_bot.choose_for_question(question)
                for option in chosen:
                    _click_option(page, option)
                if on_decision:
                    on_decision(question, chosen)

        survey_bot.sleep_range(delays["before_submit_seconds"])
        if stopped():
            return False
        with page.expect_navigation():
            page.click(f"#{SUBMIT_BUTTON_ID}")
        survey_bot.sleep_range(delays["page_change_seconds"])

    raise survey_bot.SurveyError(
        f"Опрос не завершился за {survey_bot.MAX_STEPS} шагов — похоже, бот застрял на одной странице"
    )


def run_once(config: dict, run_number: int, log, on_page=None, on_decision=None) -> bool:
    ensure_playwright(log)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _launch(playwright, config, log)
        try:
            context = browser.new_context(locale="ru-RU")
            page = context.new_page()
            try:
                return complete_survey(page, config, on_page=on_page, on_decision=on_decision)
            finally:
                context.close()
        finally:
            browser.close()
