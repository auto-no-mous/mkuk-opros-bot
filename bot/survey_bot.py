"""Core automation loop: launches an isolated browser profile per run and walks through the survey."""
import json
import random
import threading
import time
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright

from bot import rules
from bot.profile import random_context_options

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

# Replaced with the caller's Event (if any) at the start of run(); lets sleep_range()
# react to a Stop request immediately instead of finishing out a long delay first.
_stop_event = threading.Event()


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def sleep_range(bounds: list) -> None:
    duration = random.uniform(bounds[0], bounds[1])
    _stop_event.wait(duration)


def _click_and_wait(page: Page, selector: str, delays: dict) -> None:
    with page.expect_navigation():
        page.click(selector)
    sleep_range(delays["page_change_seconds"])


def _click_next(page: Page, delays: dict) -> None:
    _click_and_wait(page, "#ls-button-submit", delays)


def _select(radio_input: Locator) -> None:
    """Selects a radio option the way a real user would.

    Some answer styles (e.g. the gender buttons) hide the native input behind
    Bootstrap's `.btn-check` (pointer-events: none), so clicking the input itself
    doesn't register -- the visible <label> has to be clicked instead. Other
    styles (matrix table cells) hide the label and only the input is clickable.
    """
    page = radio_input.page
    input_id = radio_input.get_attribute("id")
    label = page.locator(f"label[for='{input_id}']")
    if label.count() > 0 and label.first.is_visible():
        label.first.click(force=True)
    else:
        radio_input.check(force=True)


def _answer_single_choice(question: Locator) -> None:
    text = question.locator(".question-text").inner_text().strip()
    fixed_answer = rules.find_fixed_answer(text)

    if fixed_answer is not None:
        label = question.locator("label", has_text=fixed_answer).first
        input_id = label.get_attribute("for")
        _select(question.page.locator(f"#{input_id}"))
        return

    radios = question.locator("input[type='radio']")
    _select(radios.nth(random.randrange(radios.count())))


def _answer_matrix(question: Locator) -> None:
    rows = question.locator("table tbody tr")
    row_count = rows.count()
    for i in range(row_count):
        row = rows.nth(i)
        radios = row.locator("input[type='radio']")
        if i == row_count - 1:
            column = random.choice(rules.MATRIX_LAST_ROW_COLUMNS)
        else:
            column = rules.MATRIX_DEFAULT_COLUMN
        _select(radios.nth(column))


def answer_question_page(page: Page) -> None:
    questions = page.locator(".question-container")
    for i in range(questions.count()):
        question = questions.nth(i)
        if question.locator("table").count() > 0:
            _answer_matrix(question)
        else:
            _answer_single_choice(question)


def complete_survey(page: Page, config: dict) -> None:
    delays = config["delays"]
    page.goto(config["survey_url"])
    sleep_range(delays["page_change_seconds"])

    while True:
        if page.locator(".completed-wrapper").count() > 0:
            return
        if page.locator(".ap-org-welcome-button").count() > 0:
            # Organization confirmation gate ("Вы оставляете оценку деятельности...").
            # Shown on every fresh session since it isn't part of the LimeSurvey engine itself.
            _click_and_wait(page, ".ap-org-welcome-button", delays)
            continue
        if page.locator("#welcome-container").count() == 0:
            answer_question_page(page)
        sleep_range(delays["before_submit_seconds"])
        _click_next(page, delays)


def _dump_debug_snapshot(page: Page, run_number: int, log) -> None:
    debug_dir = ROOT / "debug"
    debug_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base = debug_dir / f"run{run_number}_{stamp}"
    try:
        page.screenshot(path=str(base) + ".png", full_page=True)
        (base.with_suffix(".html")).write_text(page.content(), encoding="utf-8")
        log(f"Сохранил скриншот и HTML страницы, на которой произошла ошибка: {base}.png / {base}.html")
    except Exception as exc:  # noqa: BLE001
        log(f"Не удалось сохранить отладочный снимок страницы: {exc}")


def run_once(browser, config: dict, run_number: int, log) -> None:
    context_options = random_context_options() if config["browser"]["randomize_fingerprint"] else {}
    context = browser.new_context(**context_options)
    page = context.new_page()
    try:
        complete_survey(page, config)
    except Exception:
        _dump_debug_snapshot(page, run_number, log)
        raise
    finally:
        context.close()


def run(stop_event: threading.Event = None, log=print, on_run_done=None) -> None:
    """Runs the bot loop.

    stop_event: when set, the loop stops after the current in-progress survey run
        (and skips the remaining between-runs delay) instead of finishing all `runs`.
    log: called with a str message for every progress update; defaults to print()
        for plain CLI usage, but a GUI can pass something that pushes to a queue.
    on_run_done: called with (run_number, success: bool) after each attempt, for
        callers that want structured progress instead of parsing log text.
    """
    global _stop_event
    _stop_event = stop_event or threading.Event()

    config = load_config()
    runs = config.get("runs", 0)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.get("headless", False))
        try:
            count = 0
            while (runs == 0 or count < runs) and not _stop_event.is_set():
                count += 1
                log(f"--- Прохождение опроса #{count} ---")
                success = True
                try:
                    run_once(browser, config, count, log)
                    log(f"Опрос #{count} пройден успешно.")
                except Exception as exc:  # noqa: BLE001
                    success = False
                    log(f"Ошибка при прохождении опроса #{count}: {exc}")
                if on_run_done:
                    on_run_done(count, success)
                if (runs == 0 or count < runs) and not _stop_event.is_set():
                    sleep_range(config["delays"]["between_runs_seconds"])
            log("Бот остановлен." if _stop_event.is_set() else "Бот завершил все прохождения.")
        finally:
            browser.close()


if __name__ == "__main__":
    run()
