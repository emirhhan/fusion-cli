"""Small subprocess entrypoint used by the control panel to open a login browser."""

from __future__ import annotations

import argparse
import asyncio

from .web_browser import open_login_browser


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("provider")
    parser.add_argument("account")
    args = parser.parse_args()
    asyncio.run(open_login_browser(args.provider, args.account))


if __name__ == "__main__":
    main()
