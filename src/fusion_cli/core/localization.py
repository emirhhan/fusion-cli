"""Araçla ölçülen kaynak konumlarının içerik taşımayan değerleri."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

MAX_LOCALIZATION_CANDIDATES = 5
MAX_LOCALIZATION_LABEL_CHARS = 160
MAX_LOCALIZATION_PATH_CHARS = 1024
MAX_LOCALIZATION_PROMPT_CHARS = 8192
_PYTHON_SUFFIXES = frozenset({".py", ".pyi"})


@dataclass(frozen=True, slots=True)
class LocalizationCandidate:
    """Tek gerçek çağrıya ve kaynak baytlarına bağlı aday."""

    path: str
    symbol: str
    evidence_call_id: str
    source_digest: str


@dataclass(frozen=True, slots=True)
class LocalizationCard:
    """En çok beş aday; belirsizlik ve sonraki arama önerisi."""

    candidates: tuple[LocalizationCandidate, ...] = ()
    uncertainty: str = "Henüz güncel araç kanıtı yok."
    next_search: str = "Görevde açık dosya varsa önce o dosyada ara; aksi halde aramayı genişlet."

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", self.candidates[:MAX_LOCALIZATION_CANDIDATES])
        object.__setattr__(self, "uncertainty", self.uncertainty[:MAX_LOCALIZATION_LABEL_CHARS])
        object.__setattr__(self, "next_search", self.next_search[:MAX_LOCALIZATION_LABEL_CHARS])


@dataclass(slots=True)
class LocalizationState:
    """Aynı araç bağlamını paylaşan plan adımlarının güncel kartı."""

    enabled: bool = False
    card: LocalizationCard = field(default_factory=LocalizationCard)


def localization_symbol(source: str, line_number: int, path: Path) -> str:
    """Yalnız ayrıştırılmış kaynak tanımını sembol say; yorum/metni kabul etme.

    Desteklenmeyen dil veya bozuk kaynak için dosya etiketi kullanılır; bir
    metin regex'i yorum/doküman içeriğini tanım gibi göstermez.
    """
    fallback = path.stem[:MAX_LOCALIZATION_LABEL_CHARS]
    if path.suffix not in _PYTHON_SUFFIXES:
        return fallback
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return fallback
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.lineno == line_number
        ):
            return node.name[:MAX_LOCALIZATION_LABEL_CHARS]
    return fallback
