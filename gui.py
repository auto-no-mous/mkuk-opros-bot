"""Tkinter GUI: edit config.json visually, start/stop the bot, and watch its progress live."""
from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

from bot import survey_bot

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"

DEFAULT_CONFIG = {
    "survey_url": "",
    "runs": 0,
    "headless": False,
    "delays": {
        "page_change_seconds": [10, 30],
        "before_submit_seconds": [5, 10],
        "between_runs_seconds": [15, 45],
    },
    "browser": {"randomize_fingerprint": True},
}


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Бот для прохождения опросов МКУК, для клубов, ДК")
        self.root.geometry("560x560")
        self.root.minsize(480, 460)

        self.log_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.bot_thread: threading.Thread | None = None
        self.ok_count = 0
        self.error_count = 0
        self.total_runs = 0

        self.vars: dict[str, tk.Variable] = {}
        self._build_ui()
        self._load_config_into_fields()

        self.root.after(100, self._poll_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- UI construction ----------
    def _build_ui(self) -> None:
        settings = ttk.LabelFrame(self.root, text="Настройки")
        settings.pack(fill="x", padx=10, pady=10)

        self.vars["survey_url"] = tk.StringVar()
        self._add_entry(settings, "Ссылка на опрос:", "survey_url", width=50)

        self.vars["runs"] = tk.StringVar()
        self._add_entry(settings, "Число прохождений (0 = без ограничений):", "runs", width=10)

        self.vars["headless"] = tk.BooleanVar()
        ttk.Checkbutton(
            settings, text="Скрывать окно браузера (headless)", variable=self.vars["headless"]
        ).pack(anchor="w", padx=8, pady=(2, 2))

        self.vars["randomize_fingerprint"] = tk.BooleanVar()
        ttk.Checkbutton(
            settings,
            text='Каждый раз новый "отпечаток" браузера (User-Agent, экран, часовой пояс)',
            variable=self.vars["randomize_fingerprint"],
        ).pack(anchor="w", padx=8, pady=(0, 8))

        delays = ttk.LabelFrame(self.root, text="Задержки, секунды (мин / макс)")
        delays.pack(fill="x", padx=10, pady=(0, 10))

        self.vars["page_change_min"] = tk.StringVar()
        self.vars["page_change_max"] = tk.StringVar()
        self._add_range(delays, "Между сменой страниц:", "page_change_min", "page_change_max")

        self.vars["before_submit_min"] = tk.StringVar()
        self.vars["before_submit_max"] = tk.StringVar()
        self._add_range(delays, "Перед отправкой страницы:", "before_submit_min", "before_submit_max")

        self.vars["between_runs_min"] = tk.StringVar()
        self.vars["between_runs_max"] = tk.StringVar()
        self._add_range(delays, "Между прохождениями опроса:", "between_runs_min", "between_runs_max")

        controls = ttk.Frame(self.root)
        controls.pack(fill="x", padx=10, pady=(0, 10))

        self.start_button = ttk.Button(controls, text="Сохранить и запустить", command=self._on_start)
        self.start_button.pack(side="left")

        self.stop_button = ttk.Button(controls, text="Остановить", command=self._on_stop, state="disabled")
        self.stop_button.pack(side="left", padx=(8, 0))

        self.status_var = tk.StringVar(value="Не запущен")
        ttk.Label(controls, textvariable=self.status_var).pack(side="left", padx=(16, 0))

        self.counters_var = tk.StringVar(value="Успешно: 0   Ошибок: 0")
        ttk.Label(controls, textvariable=self.counters_var).pack(side="right")

        progress_frame = ttk.Frame(self.root)
        progress_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))

        self.progress_label_var = tk.StringVar(value="Прогонов пройдено: 0 / 0")
        ttk.Label(progress_frame, textvariable=self.progress_label_var).pack(anchor="w")

        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate", maximum=100, value=0)
        self.progress_bar.pack(fill="x", pady=(2, 0))

        log_frame = ttk.LabelFrame(self.root, text="Журнал")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_widget = scrolledtext.ScrolledText(log_frame, state="disabled", wrap="word", height=10)
        self.log_widget.pack(fill="both", expand=True)

    def _add_entry(self, parent: ttk.LabelFrame, label: str, key: str, width: int = 30) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=8, pady=4)
        ttk.Label(row, text=label, width=38).pack(side="left")
        ttk.Entry(row, textvariable=self.vars[key], width=width).pack(side="left", fill="x", expand=True)

    def _add_range(self, parent: ttk.LabelFrame, label: str, min_key: str, max_key: str) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=8, pady=4)
        ttk.Label(row, text=label, width=28).pack(side="left")
        ttk.Entry(row, textvariable=self.vars[min_key], width=8).pack(side="left")
        ttk.Label(row, text=" – ").pack(side="left")
        ttk.Entry(row, textvariable=self.vars[max_key], width=8).pack(side="left")

    # ---------- config <-> fields ----------
    def _load_config_into_fields(self) -> None:
        config = DEFAULT_CONFIG
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                messagebox.showwarning(
                    "Настройки",
                    f"Не удалось прочитать config.json, использую значения по умолчанию.\n{exc}",
                )

        self.vars["survey_url"].set(config.get("survey_url", ""))
        self.vars["runs"].set(str(config.get("runs", 0)))
        self.vars["headless"].set(bool(config.get("headless", False)))

        delays = config.get("delays", DEFAULT_CONFIG["delays"])
        page_change = delays.get("page_change_seconds", [10, 30])
        before_submit = delays.get("before_submit_seconds", [5, 10])
        between_runs = delays.get("between_runs_seconds", [15, 45])
        self.vars["page_change_min"].set(page_change[0])
        self.vars["page_change_max"].set(page_change[1])
        self.vars["before_submit_min"].set(before_submit[0])
        self.vars["before_submit_max"].set(before_submit[1])
        self.vars["between_runs_min"].set(between_runs[0])
        self.vars["between_runs_max"].set(between_runs[1])

        browser = config.get("browser", {})
        self.vars["randomize_fingerprint"].set(bool(browser.get("randomize_fingerprint", True)))

    def _read_fields_into_config(self) -> dict:
        def as_float(key: str, field_label: str) -> float:
            raw = self.vars[key].get().strip().replace(",", ".")
            try:
                return float(raw)
            except ValueError:
                raise ValueError(f'«{field_label}» должно быть числом (введено: {raw!r})') from None

        def as_int(key: str, field_label: str) -> int:
            raw = self.vars[key].get().strip()
            try:
                return int(raw)
            except ValueError:
                raise ValueError(f'«{field_label}» должно быть целым числом (введено: {raw!r})') from None

        def as_range(min_key: str, max_key: str, field_label: str) -> list:
            lo = as_float(min_key, field_label + " (мин)")
            hi = as_float(max_key, field_label + " (макс)")
            if lo < 0 or hi < 0:
                raise ValueError(f"«{field_label}»: значения не могут быть отрицательными.")
            if lo > hi:
                raise ValueError(f"«{field_label}»: минимум больше максимума.")
            return [lo, hi]

        url = self.vars["survey_url"].get().strip()
        if not url:
            raise ValueError("Укажите ссылку на опрос.")

        runs = as_int("runs", "Число прохождений")
        if runs < 0:
            raise ValueError("Число прохождений не может быть отрицательным.")

        return {
            "survey_url": url,
            "runs": runs,
            "headless": bool(self.vars["headless"].get()),
            "delays": {
                "page_change_seconds": as_range(
                    "page_change_min", "page_change_max", "Между сменой страниц"
                ),
                "before_submit_seconds": as_range(
                    "before_submit_min", "before_submit_max", "Перед отправкой страницы"
                ),
                "between_runs_seconds": as_range(
                    "between_runs_min", "between_runs_max", "Между прохождениями опроса"
                ),
            },
            "browser": {"randomize_fingerprint": bool(self.vars["randomize_fingerprint"].get())},
        }

    # ---------- actions ----------
    def _on_start(self) -> None:
        try:
            config = self._read_fields_into_config()
        except ValueError as exc:
            messagebox.showerror("Проверьте настройки", str(exc))
            return

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        self.ok_count = 0
        self.error_count = 0
        self.total_runs = config["runs"]
        self._update_counters()
        self._reset_progress()
        self._clear_log()
        self._append_log("Запускаю бота...")

        self.stop_event = threading.Event()
        self._set_running_state(True)

        self.bot_thread = threading.Thread(target=self._run_bot, daemon=True)
        self.bot_thread.start()

    def _run_bot(self) -> None:
        try:
            survey_bot.run(
                stop_event=self.stop_event,
                log=lambda msg: self.log_queue.put(("log", msg)),
                on_run_done=lambda run_number, ok: self.log_queue.put(("progress", run_number, ok)),
            )
        except Exception as exc:  # noqa: BLE001
            self.log_queue.put(("log", f"Бот аварийно завершился: {exc}"))
        finally:
            self.log_queue.put(("finished", None))

    def _on_stop(self) -> None:
        self.stop_event.set()
        self.stop_button.configure(state="disabled")
        self._append_log("Останавливаю бота (после текущего прохождения)...")

    def _on_close(self) -> None:
        if self.bot_thread and self.bot_thread.is_alive():
            if not messagebox.askyesno("Закрыть?", "Бот ещё работает. Остановить его и закрыть окно?"):
                return
            self.stop_event.set()
        self.root.destroy()

    # ---------- helpers ----------
    def _set_running_state(self, running: bool) -> None:
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        self.status_var.set("Работает..." if running else "Остановлен")

    def _append_log(self, text: str) -> None:
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", text + "\n")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_widget.configure(state="normal")
        self.log_widget.delete("1.0", "end")
        self.log_widget.configure(state="disabled")

    def _update_counters(self) -> None:
        self.counters_var.set(f"Успешно: {self.ok_count}   Ошибок: {self.error_count}")

    def _reset_progress(self) -> None:
        self.progress_bar.stop()
        if self.total_runs > 0:
            self.progress_bar.configure(mode="determinate", maximum=self.total_runs, value=0)
        else:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start(50)
        self._update_progress_label(0)

    def _update_progress_label(self, completed: int) -> None:
        total_text = str(self.total_runs) if self.total_runs > 0 else "∞"
        self.progress_label_var.set(f"Прогонов пройдено: {completed} / {total_text}")

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self.log_queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    self._append_log(item[1])
                elif kind == "progress":
                    _, run_number, ok = item
                    if ok:
                        self.ok_count += 1
                    else:
                        self.error_count += 1
                    self._update_counters()
                    completed = self.ok_count + self.error_count
                    if self.total_runs > 0:
                        self.progress_bar["value"] = completed
                    self._update_progress_label(completed)
                    self.status_var.set(f"Работает... (прогон #{run_number})")
                elif kind == "finished":
                    self.progress_bar.stop()
                    self._set_running_state(False)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
