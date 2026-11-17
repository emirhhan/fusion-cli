"""PyInstaller ikilisinin başlangıç noktası: mevcut Typer uygulamasını çalıştırır."""

import os
import sys


def main() -> None:
    if getattr(sys, "frozen", False):
        # Playwright otherwise forces a hermetic .local-browsers directory for
        # frozen apps. Our runtime uses separately installed browsers; an empty
        # value retains Playwright's normal platform cache and explicit overrides.
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "")

    from fusion_cli.cli.app import main as run_cli

    run_cli()


if __name__ == "__main__":
    main()
