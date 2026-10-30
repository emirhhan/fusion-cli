"""Web (tarayıcı) taşımasının her araç turunda tekrarladığı nihai cevap sözleşmesi.

Metin eskiden `providers/web_browser.py` içinde SABİTTİ ve taşıma katmanı hangi
araçların sunulduğunu bilmediği için (P1-33):

- plan modunda / salt-okunur kümede `todo_write` ya da `ask_user` yokken modele var
  olmayan aracı çağırmasını söylüyordu,
- her devam turunda "İLK iş todo_write ile plan yaz" cümlesini yineliyor, model her
  turda yeniden plan yapmaya çalışabiliyordu.

Artık sözleşmeyi, sunulan araç adlarını ve görev listesinin durumunu bilen motor üretir
ve `CompletionRequest.answer_contract` ile taşır; taşıma yalnızca yerleştirir. Metin
parçaları `prompts/web_answer_contract.md` dosyasındadır.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from functools import cache
from pathlib import Path

_CONTRACT_FILE = Path(__file__).parent / "prompts" / "web_answer_contract.md"
_SECTION_PREFIX = "## "

_PLAN_TOOL = "todo_write"
_ASK_TOOL = "ask_user"


@cache
def _sections() -> Mapping[str, str]:
    """`## ad` başlıklı bölümleri sözlüğe çevir (dosya bir kez okunur)."""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in _CONTRACT_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith(_SECTION_PREFIX):
            current = sections.setdefault(line[len(_SECTION_PREFIX) :].strip(), [])
        elif current is not None:
            current.append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def tool_names(tools: tuple[Mapping[str, object], ...]) -> frozenset[str]:
    """Function-calling şemalarından araç adlarını çıkar."""
    names: set[str] = set()
    for schema in tools:
        function = schema.get("function")
        name = function.get("name") if isinstance(function, Mapping) else None
        if isinstance(name, str):
            names.add(name)
    return frozenset(names)


def render_answer_contract(offered: Collection[str], *, has_todos: bool) -> str:
    """Sunulan araçlara ve plan durumuna göre sözleşme metnini üret.

    `offered` boşsa (araçsız çağrı) boş döner: sözleşme araç turlarına aittir.
    """
    if not offered:
        return ""
    sections = _sections()
    parts: list[str] = []
    if _PLAN_TOOL in offered:
        parts.append(sections["plan_surer" if has_todos else "plan_yeni"])
    parts.append(sections["acilis"])
    parts.append(sections["soru_var" if _ASK_TOOL in offered else "soru_yok"])
    parts.append(sections["kapanis"])
    parts.append(sections["durustluk"])
    return "\n".join(parts)
