"""Web işi araçları: site tarama ve görseli web için hazırlama.

Temel araç defterinde değil burada kayıtlıdır: web modellerine giden temel araç
istemi ölçülmüş bir bütçeyle sınırlı (`tests/test_tool_emulation_diet.py`).
Bu araçlar `generate_image` gibi motorun alan araçlarıdır.
"""

from __future__ import annotations

from ...core.tools import Tool
from ...tools.crawl import site_crawl
from ...tools.image_ops import optimize_image

_STRING = {"type": "string"}


def web_work_tools() -> tuple[Tool, ...]:
    return (
        Tool(
            name="site_crawl",
            description="Siteyi aynı alan adında gez (robots.txt'ye uyar): başlıklar ve "
            "görsel listesi. Tek sayfa için web_fetch.",
            parameters={
                "type": "object",
                "properties": {
                    "url": _STRING,
                    "max_pages": {"type": "integer"},
                    "max_depth": {"type": "integer"},
                },
                "required": ["url"],
            },
            run=site_crawl,
        ),
        Tool(
            name="optimize_image",
            description="Var olan görseli web için hazırla (.webp, isteğe bağlı tam ölçü, "
            "srcset) ve <img> önerisi ver.",
            parameters={
                "type": "object",
                "properties": {
                    "path": _STRING,
                    "out": _STRING,
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                    "alt": _STRING,
                    "ilk_ekran": {"type": "boolean"},
                },
                "required": ["path"],
            },
            run=optimize_image,
            mutating=True,
        ),
    )
