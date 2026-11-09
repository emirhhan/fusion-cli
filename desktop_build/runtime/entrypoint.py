"""PyInstaller ikilisinin başlangıç noktası: mevcut Typer uygulamasını çalıştırır."""

import os
import sys


def main() -> None:
    if getattr(sys, "frozen", False):
        # Playwright otherwise forces a hermetic .local-browsers directory for
        # frozen apps. Our runtime uses separately installed browsers; an empty
        # value retains Playwright's normal platform cache and explicit overrides.
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "")

    if sys.argv[1:2] == ["--release-observer"]:
        if not getattr(sys, "frozen", False):
            raise SystemExit("Release observer requires the frozen runtime.")
        sys.argv.pop(1)
        from evals.frozen_engine import install

        install()

    from fusion_cli.cli.app import main as run_cli

    run_cli()


if __name__ == "__main__":
    main()
