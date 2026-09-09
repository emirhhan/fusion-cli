"""Yerel production smoke testi için sırsız Streamable HTTP MCP sunucusu."""

from __future__ import annotations

import argparse

from mcp.server.fastmcp import FastMCP


def build_server(*, port: int = 8765) -> FastMCP:
    server = FastMCP(
        "fusion-oauth-fixture",
        host="127.0.0.1",
        port=port,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )

    @server.tool()
    def ping() -> str:
        return "pong"

    return server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    build_server(port=args.port).run("streamable-http")


if __name__ == "__main__":
    main()
