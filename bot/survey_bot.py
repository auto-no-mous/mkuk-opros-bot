"""Core automation loop: walks through the survey over plain HTTP, one fresh session per run."""
import json
import random
import threading
import time
from pathlib import Path

from bot import rules
from bot.page import SurveyPage
from bot.profile import default_headers, random_headers
from bot.session import NetworkError, Session

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

# A survey page that keeps returning without ever completing would otherwise
# loop forever; no LimeSurvey questionnaire is anywhere near this long.
MAX_STEPS = 30

# Replaced with the caller's Event (if any) at the start of run(); lets sleep_range()
# and the page loop react to a Stop request immediately, instead of finishing out a
# long delay -- or a whole survey -- first.
_stop_event = threading.Event()


class SurveyError(RuntimeError):
    """The survey did not go the way the rules expect."""


class BrowserUnavailable(RuntimeError):
    """The optional browser engine could not be started.

    Defined here rather than in `browser_bot` so that this module can catch it
    without importing Playwright's side of the project.
    """


def uses_browser(config: dict) -> bool:
    return config.get("engine") == "browser"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def sleep_range(bounds: list) -> None:
    duration = random.uniform(bounds[0], bounds[1])
    _stop_event.wait(duration)


def _choose_single_choice(question) -> list:
    options = question.options()
    if not options:
        return []

    fixed_answer = rules.find_fixed_answer(question.text)
    if fixed_answer is not None:
        chosen = rules.match_option(options, fixed_answer)
        if chosen is None:
            raise SurveyError(
                f'Не нашёл вариант ответа «{fixed_answer}» в вопросе «{question.text[:80]}»'
            )
    else:
        chosen = random.choice(options)
    return [chosen]


def _choose_matrix(question) -> list:
    chosen = []
    rows = question.matrix_rows()
    for index, row in enumerate(rows):
        if index == len(rows) - 1:
            column = random.choice(rules.MATRIX_LAST_ROW_COLUMNS)
        else:
            column = rules.MATRIX_DEFAULT_COLUMN
        # Guard against a shorter row than the rules assume, so a reworded
        # survey degrades to "last available column" instead of crashing.
        chosen.append(row[min(column, len(row) - 1)])
    return chosen


def choose_for_question(question) -> list:
    """The option(s) the rules pick for one question.

    Kept separate from the posting of the form so that the check mode can watch
    a real run make its decisions rather than reimplementing the rules.
    """
    if question.is_matrix:
        return _choose_matrix(question)
    return _choose_single_choice(question)


def answer_question_page(page: SurveyPage, fields: dict, on_decision=None) -> None:
    for question in page.questions():
        chosen = choose_for_question(question)
        for option in chosen:
            fields[option.name] = option.value
        if on_decision:
            on_decision(question, chosen)


def complete_survey(session: Session, config: dict, on_page=None, on_decision=None) -> bool:
    """Walks one full pass of the survey.

    Returns True once the survey's completion page is reached, or False if a stop
    was requested part-way -- in that case nothing further is submitted, so the
    half-filled run does not reach the site at all.

    on_page: called with every page as it is loaded, so a caller can keep hold of
        the last one for the debug snapshot when something goes wrong.
    on_decision: called with (question, chosen_options) for every question answered,
        which is how the check mode reports what the rules picked.
    """
    delays = config["delays"]

    def load(page_response) -> SurveyPage:
        page = SurveyPage(page_response.url, page_response.html)
        if on_page:
            on_page(page)
        return page

    page = load(session.get(config["survey_url"]))
    sleep_range(delays["page_change_seconds"])

    for _ in range(MAX_STEPS):
        if _stop_event.is_set():
            return False
        if page.is_completed:
            return True

        gate_url = page.org_gate_url
        if gate_url is not None:
            # Organization confirmation gate ("Вы оставляете оценку деятельности...").
            # Shown on every fresh session since it isn't part of the LimeSurvey engine itself.
            page = load(session.get(gate_url, referer=page.url))
            sleep_range(delays["page_change_seconds"])
            continue

        if not page.has_form:
            raise SurveyError("На странице опроса нет формы — возможно, сайт вернул что-то неожиданное")

        fields = page.base_fields()
        if not page.is_welcome:
            answer_question_page(page, fields, on_decision=on_decision)
        fields["move"] = page.submit_move

        sleep_range(delays["before_submit_seconds"])
        if _stop_event.is_set():
            return False
        page = load(session.post(page.action_url, fields, referer=page.url))

        rejected = page.rejected_questions()
        if rejected:
            raise SurveyError("Сайт не принял ответы на вопросы: " + "; ".join(rejected))

        sleep_range(delays["page_change_seconds"])

    raise SurveyError(f"Опрос не завершился за {MAX_STEPS} шагов — похоже, бот застрял на одной странице")


def _dump_debug_snapshot(page: SurveyPage, run_number: int, log) -> None:
    debug_dir = ROOT / "debug"
    debug_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    target = debug_dir / f"run{run_number}_{stamp}.html"
    try:
        target.write_text(page.html, encoding="utf-8")
        log(f"Сохранил HTML страницы, на которой произошла ошибка: {target}")
    except OSError as exc:
        log(f"Не удалось сохранить отладочный снимок страницы: {exc}")


def session_for(config: dict) -> Session:
    randomize = config.get("requests", {}).get("randomize_fingerprint", True)
    return Session(random_headers() if randomize else default_headers())


def run_once(config: dict, run_number: int, log) -> bool:
    seen = {}

    def remember(page) -> None:
        seen["page"] = page

    try:
        if uses_browser(config):
            from bot import browser_bot

            return browser_bot.run_once(config, run_number, log, on_page=remember)
        return complete_survey(session_for(config), config, on_page=remember)
    except Exception:
        if config.get("debug_on_error", True) and "page" in seen:
            _dump_debug_snapshot(seen["page"], run_number, log)
        raise


def run(stop_event: threading.Event = None, log=print, on_run_done=None) -> None:
    """Runs the bot loop.

    stop_event: when set, the current run is abandoned without submitting the page
        it was filling in, any remaining delay is skipped, and the loop ends.
    log: called with a str message for every progress update; defaults to print()
        for plain CLI usage, but a GUI can pass something that pushes to a queue.
    on_run_done: called with (run_number, success: bool) after each run that either
        finished or failed, for callers that want structured progress instead of
        parsing log text. A run abandoned on `stop_event` is not reported: it
        neither reached the site nor went wrong.
    """
    global _stop_event
    _stop_event = stop_event or threading.Event()

    config = load_config()
    runs = config.get("runs", 0)

    count = 0
    while (runs == 0 or count < runs) and not _stop_event.is_set():
        count += 1
        log(f"--- Прохождение опроса #{count} ---")
        success = True
        finished = True
        try:
            finished = run_once(config, count, log)
            if finished:
                log(f"Опрос #{count} пройден успешно.")
            else:
                log(f"Прохождение #{count} прервано — ответ не отправлен.")
        except (SurveyError, NetworkError, BrowserUnavailable) as exc:
            success = False
            log(f"Ошибка при прохождении опроса #{count}: {exc}")
        except Exception as exc:  # noqa: BLE001
            success = False
            log(f"Непредвиденная ошибка при прохождении опроса #{count}: {exc}")
        # An interrupted run is neither a success nor a failure, so it is left
        # out of the counters entirely.
        if on_run_done and (finished or not success):
            on_run_done(count, success)
        if (runs == 0 or count < runs) and not _stop_event.is_set():
            sleep_range(config["delays"]["between_runs_seconds"])
    log("Бот остановлен." if _stop_event.is_set() else "Бот завершил все прохождения.")


if __name__ == "__main__":
    run()
