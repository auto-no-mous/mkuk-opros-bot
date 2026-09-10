"""Check mode: makes one real pass of the survey and reports every answer it chose.

The report is produced by watching the ordinary run make its decisions, so what
you see is what the bot actually does -- there is no second copy of the rules
that could drift out of step with `survey_bot`.

Note that this does submit one response. The survey gives no way to recognise its
final page in advance: every page carries the same "Продолжить" button, with the
same value, class and progress bar, so a pass that stopped one page short would
have to guess where to stop.
"""
from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

from bot import report, survey_bot
from bot.page import SurveyPage

ROOT = Path(__file__).resolve().parent.parent
PREVIEW_DIR = ROOT / "preview"


class _Recorder:
    """Collects the pages walked and the choices made, in order."""

    def __init__(self) -> None:
        self.pages: list = []

    def on_page(self, page: SurveyPage) -> None:
        self.pages.append({"page": page, "decisions": [], "title": "", "raw_file": ""})

    def on_decision(self, question, chosen) -> None:
        if self.pages:
            self.pages[-1]["decisions"].append((question, chosen))

    def describe(self) -> list:
        """Titles the pages and drops the ones that carry no information."""
        described = []
        step = 0
        for entry in self.pages:
            page = entry["page"]
            if page.org_gate_url is not None:
                entry["title"] = "Подтверждение организации"
            elif page.is_welcome:
                entry["title"] = "Приветственная страница"
            elif page.is_completed:
                entry["title"] = "Страница завершения опроса"
            else:
                step += 1
                entry["title"] = f"Страница {step}"
            described.append(entry)
        return described


def _walk(config: dict, recorder: "_Recorder", log) -> bool:
    """One pass with whichever engine is configured, reporting every choice."""
    if survey_bot.uses_browser(config):
        from bot import browser_bot

        return browser_bot.run_once(
            config, 1, log, on_page=recorder.on_page, on_decision=recorder.on_decision
        )
    return survey_bot.complete_survey(
        survey_bot.session_for(config),
        config,
        on_page=recorder.on_page,
        on_decision=recorder.on_decision,
    )


def _write_raw_pages(entries: list) -> None:
    for index, entry in enumerate(entries, start=1):
        name = f"page{index}.html"
        (PREVIEW_DIR / name).write_text(entry["page"].html, encoding="utf-8")
        entry["raw_file"] = name


def run_check(log=print, stop_event: threading.Event = None, open_browser: bool = True) -> Path:
    """Runs one survey pass and writes preview/report.html. Returns the report path."""
    survey_bot._stop_event = stop_event or threading.Event()

    config = survey_bot.load_config()
    survey_url = config["survey_url"]
    recorder = _Recorder()

    if survey_bot.uses_browser(config):
        log("Проверка в браузере: сейчас откроется окно, опрос пройдёт у вас на глазах...")
    else:
        log("Проверка: прохожу опрос один раз и записываю каждый выбор...")

    error = None
    outcome = ""
    try:
        finished = _walk(config, recorder, log)
        outcome = (
            "Опрос пройден полностью — бот дошёл до страницы завершения."
            if finished
            else "Проверка прервана — опрос не был пройден до конца."
        )
        log(outcome)
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
        log(f"Проверка завершилась ошибкой: {error}")

    entries = recorder.describe()
    PREVIEW_DIR.mkdir(exist_ok=True)
    _write_raw_pages(entries)

    report_path = PREVIEW_DIR / "report.html"
    report_path.write_text(
        report.build(entries, survey_url, outcome, error), encoding="utf-8"
    )
    log(f"Отчёт о проверке: {report_path}")

    if open_browser:
        webbrowser.open(report_path.as_uri())
    return report_path


if __name__ == "__main__":
    run_check()
