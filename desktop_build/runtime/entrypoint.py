"""PyInstaller ikilisinin başlangıç noktası: mevcut Typer uygulamasını çalıştırır."""

import os
import sys
from pathlib import Path


def main() -> None:
    if getattr(sys, "frozen", False):
        # tiktoken data must be usable before LiteLLM/CLI imports, without an
        # online first-run download. Explicit cache paths (including empty)
        # retain tiktoken's own precedence and opt-out semantics.
        from fusion_cli.config.loader import load_dotenv_environment

        load_dotenv_environment(keys=frozenset({"TIKTOKEN_CACHE_DIR", "DATA_GYM_CACHE_DIR"}))
        if "TIKTOKEN_CACHE_DIR" not in os.environ and "DATA_GYM_CACHE_DIR" not in os.environ:
            bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
            tokenizers = bundle / "fusion-tokenizer-cache"
            if tokenizers.is_dir():
                os.environ["TIKTOKEN_CACHE_DIR"] = str(tokenizers)
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
