"""Fusion öz-bilgisi: her modele (yerel, API, web) Fusion'ın ne olduğunu ve elindeki
araç ailelerini bildirir.

Statik kılavuz (`prompts/fusion_bilgi.md`) ürünü anlatır; dinamik satır ise BU turda
gerçekten sunulan araç ailelerini ve öğretmeni listeler. Böylece model hem "Fusion
neler yapar" sorusuna doğru cevap verir hem de elinde olmayan bir şeyi varmış gibi
kullanmaz.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

GUIDE = (Path(__file__).parent / "prompts" / "fusion_bilgi.md").read_text(encoding="utf-8")

#: Araç ailesi etiketi → o ailenin araç adı önekleri/adları.
_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("kod ve dosya", ("read_file", "edit_file", "write_file", "run_shell", "search_code")),
    ("Chrome eklentisi (gerçek Chrome)", ("chrome_",)),
    ("Fusion Browser", ("browser_",)),
    ("masaüstü kontrolü", ("desktop_",)),
    ("öğretmen", ("ask_teacher",)),
    ("çoklu-model danışma", ("council",)),
    ("ders belleği", ("recall_lessons",)),
    ("beceri ve ajanlar", ("find_skill", "find_agent", "invoke_agent", "spawn_agent")),
    ("görsel/video", ("generate_image", "render_remotion", "scaffold_remotion")),
    ("site araçları", ("scaffold_web", "start_preview", "site_design", "clone_site")),
    ("arka plan işleri", ("start_job", "job_status")),
)


def _present(names: Iterable[str], needles: tuple[str, ...]) -> bool:
    pool = tuple(names)
    return any(
        name.startswith(needle) if needle.endswith("_") else name == needle
        for needle in needles
        for name in pool
    )


def session_line(tool_names: Iterable[str], teacher_model: str = "") -> str:
    """Bu turda sunulan aileleri tek satırda özetle."""
    names = tuple(tool_names)
    families = [label for label, needles in _FAMILIES if _present(names, needles)]
    missing = [
        label for label in ("Chrome eklentisi (gerçek Chrome)", "öğretmen") if label not in families
    ]
    parts = ["Bu turda elindeki aileler: " + ", ".join(families) + "."]
    if teacher_model and "öğretmen" in families:
        parts.append(f"Öğretmen: {teacher_model}.")
    if missing:
        parts.append("Şu an KAPALI olanlar: " + ", ".join(missing) + ".")
    return " ".join(parts)


def knowledge_block(tool_names: Iterable[str], teacher_model: str = "") -> str:
    """Sistem istemine eklenecek tam blok."""
    return f"{GUIDE}\n{session_line(tool_names, teacher_model)}"
