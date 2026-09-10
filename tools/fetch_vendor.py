"""Downloads the Playwright wheels into vendor/, for carrying to an offline machine.

Run this once where pip works (with a VPN if needed), then copy the whole project
folder -- vendor/ included -- to the machine that has no access. The browser mode
installs from that folder without touching the network.

    python tools/fetch_vendor.py                 # for the Python running this
    python tools/fetch_vendor.py 3.10 3.11 3.12  # plus these Python versions

Why versions matter: `greenlet` ships as a compiled wheel built per Python
version, so a vendor folder filled on Python 3.12 will not install on 3.10.
Everything else in the set is version-independent.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = ROOT / "vendor"

# Only the compiled dependency has to be fetched again per Python version.
PER_VERSION_PACKAGES = ["greenlet"]


def run(args: list) -> bool:
    print("$", " ".join(args))
    return subprocess.run(args, cwd=str(ROOT)).returncode == 0


def main() -> None:
    versions = sys.argv[1:]
    VENDOR_DIR.mkdir(exist_ok=True)

    ok = run([sys.executable, "-m", "pip", "download", "playwright", "-d", str(VENDOR_DIR)])
    if not ok:
        print("\nНе удалось скачать Playwright. Проверьте доступ к pypi.org (нужен VPN?).")
        sys.exit(1)

    for version in versions:
        for package in PER_VERSION_PACKAGES:
            run([
                sys.executable, "-m", "pip", "download", package,
                "--only-binary=:all:", "--python-version", version,
                "-d", str(VENDOR_DIR),
            ])

    wheels = sorted(VENDOR_DIR.glob("*.whl"))
    total_mb = sum(w.stat().st_size for w in wheels) / 1048576
    print(f"\nГотово: {len(wheels)} файлов, {total_mb:.1f} МБ в {VENDOR_DIR}")
    for wheel in wheels:
        print(f"  {wheel.name}  ({wheel.stat().st_size / 1048576:.1f} МБ)")
    print(
        "\nБраузер качать не нужно: режим использует установленные Edge или Chrome.\n"
        "Если их на машине нет — там же выполните: python -m playwright install chromium"
    )


if __name__ == "__main__":
    main()
