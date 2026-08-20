"""Launcher: checks Python version, installs dependencies if needed, then starts the survey bot."""
import importlib.util
import subprocess
import sys
from pathlib import Path

MIN_PYTHON = (3, 9)
ROOT = Path(__file__).resolve().parent


def setup_console_encoding() -> None:
    """Switches the Windows console to UTF-8 so Russian text prints correctly.

    Doing this from Python (rather than `chcp` inside start.bat) avoids cmd.exe's
    batch-file encoding quirks, which previously mangled Cyrillic text into
    garbage commands like "'cho' is not recognized".
    """
    if sys.platform != "win32":
        return
    subprocess.run(
        ["chcp", "65001"],
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def fail(message: str) -> None:
    print("\n" + "=" * 60)
    print("ОШИБКА")
    print("=" * 60)
    print(message)
    print("=" * 60)
    input("\nНажмите Enter, чтобы закрыть окно...")
    sys.exit(1)


def check_python_version() -> None:
    if sys.version_info < MIN_PYTHON:
        fail(
            f"Требуется Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} или новее.\n"
            f"У вас установлен Python {sys.version_info[0]}.{sys.version_info[1]}.\n"
            "Скачайте актуальную версию: https://www.python.org/downloads/"
        )


def is_installed(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def pip_install(requirements_file: Path) -> None:
    print("Устанавливаю зависимости Python (это может занять пару минут)...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        fail(
            "Не удалось установить зависимости Python через pip.\n"
            "Проверьте подключение к интернету и попробуйте запустить заново."
        )


def install_playwright_browser() -> None:
    print("Проверяю/устанавливаю браузер Chromium для Playwright...")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        fail(
            "Не удалось установить браузер Chromium для Playwright.\n"
            "Проверьте подключение к интернету и попробуйте запустить заново."
        )


def main() -> None:
    setup_console_encoding()
    check_python_version()

    requirements_file = ROOT / "requirements.txt"
    if not is_installed("playwright"):
        pip_install(requirements_file)

    install_playwright_browser()

    try:
        import gui
    except ImportError as exc:
        fail(
            f"Не удалось загрузить графический интерфейс: {exc}\n"
            "Похоже, ваша установка Python собрана без модуля tkinter. "
            "Переустановите Python с сайта https://www.python.org/downloads/ "
            "(стандартный установщик включает tkinter)."
        )
        return
    except Exception as exc:  # noqa: BLE001
        fail(f"Не удалось запустить бота: {exc}")
        return

    try:
        gui.main()
    except Exception as exc:  # noqa: BLE001
        fail(f"Бот завершился с ошибкой: {exc}")


if __name__ == "__main__":
    main()
