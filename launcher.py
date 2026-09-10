"""Launcher: checks that this Python can run the bot, then starts it.

The bot uses only the Python standard library, so there is nothing to download
or install here -- this exists to turn the two things that can still go wrong
(too old a Python, a build without tkinter) into a readable message.
"""
import subprocess
import sys

MIN_PYTHON = (3, 9)


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


def main() -> None:
    setup_console_encoding()
    check_python_version()

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
