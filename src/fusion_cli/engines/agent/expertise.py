"""Dar ve yüksek güvenli uzmanlık notu: görev türü kesin anlaşılınca kısa beceri özeti.

Ölçüldü: model becerileri kendisi çekmiyor (5.-17. koşuların 1.696 araç çağrısında
find_skill/read_skill 0; Hermes'in "Skills (mandatory)" istemi de aynı modelde 0
çağrı verdi). Öte yandan tur başına GENİŞ uzmanlık basmak geçmişte zarar verdi:
WEBSITE sanılan bir turda 21 KB'lık web referansı yanlış bağlam oldu (bkz.
`loop.py`). Bu yüzden burada:

- yalnız açık anahtar kelimeyle eşleşen TEK beceri seçilir (belirsizse hiçbiri),
- metin kısa tutulur (`MAX_EXPERTISE_CHARS`), tamamının yolu verilir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ...config.paths import bundled_skills_dir
from ...core.events import EventPublisher, SkillLoaded
from ...core.text_fold import fold_tr
from ...tools.capabilities import CapabilityRegistry
from ...tools.skill_pages import read_skill_page

#: Modele basılacak beceri metninin üst sınırı (karakter). Yerleşik beceriler bu
#: sınıra sığacak şekilde yazıldı (~3 KB); 21 KB'lık eski referansın yedide biri.
MAX_EXPERTISE_CHARS = 4_000


@dataclass(frozen=True, slots=True)
class _Rule:
    skill: str
    pattern: re.Pattern[str]
    exclude: re.Pattern[str] | None = None


#: Sıra önceliktir: ilk eşleşen kural kazanır (Remotion videosu da "animasyonlu"dur).
_RULES = (
    _Rule("remotion-video", re.compile(r"\bremotion\b", re.IGNORECASE)),
    _Rule(
        "html-oyun",
        re.compile(
            # `oyun(?!c)`: "oyuncak/oyuncu/oyunculuk" oyun DEĞİLDİR (A1-32).
            r"(?:\boyun(?!c)|\bgame\b).{0,80}(?:html|canvas|tarayıcı|browser|web)"
            r"|(?:html|canvas|tarayıcı|browser|web).{0,80}(?:\boyun(?!c)|\bgame\b)",
            re.IGNORECASE | re.DOTALL,
        ),
        exclude=re.compile(r"godot|unity|unreal", re.IGNORECASE),
    ),
    _Rule(
        "hareket",
        re.compile(r"animasyon|animated|animation|hareketli|motion design", re.IGNORECASE),
        exclude=re.compile(r"godot|video|remotion", re.IGNORECASE),
    ),
)


def _skill_body(folder: Path, name: str) -> str:
    try:
        metin = (folder / name / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    # Ön madde (--- … ---) modele gerekmez; adı ve yolu aşağıda verilir.
    govde = metin.split("---", 2)[-1].strip() if metin.startswith("---") else metin
    # Beceri yanındaki dosyalara (ör. remotion-video/kit) gerçek yolla başvurabilsin.
    govde = govde.replace("{SKILL_DIR}", str(folder / name))
    return govde[:MAX_EXPERTISE_CHARS]


def expertise_hint(
    task: str,
    skills_dir: Path | None = None,
    *,
    registry: CapabilityRegistry | None = None,
    publisher: EventPublisher | None = None,
) -> str | None:
    """Tek açık uzmanlığı gerçek katalog kaynağından, toplam sınır içinde yükle."""
    matches = [
        rule
        for rule in _RULES
        if rule.pattern.search(task) is not None
        and (rule.exclude is None or rule.exclude.search(task) is None)
    ]
    if len(matches) != 1:
        return None
    rule = matches[0]
    if registry is None:
        body = _skill_body(skills_dir or bundled_skills_dir(), rule.skill)
        if not body:
            return None
        prefix = f"UZMANLIK NOTU ({rule.skill} becerisi; tamamı read_skill('{rule.skill}')):\n"
        return (prefix + body)[:MAX_EXPERTISE_CHARS]
    skill = registry.get_skill(rule.skill)
    if skill is None:
        return None
    prefix = f"UZMANLIK NOTU ({skill.name}; tamamı read_skill('{skill.qualified_name}')):\n"
    page = read_skill_page(skill.path, budget=MAX_EXPERTISE_CHARS - len(prefix))
    if page.error or not page.text:
        return None
    body = page.text.replace("{SKILL_DIR}", str(skill.path.parent))
    prompt = (prefix + body)[:MAX_EXPERTISE_CHARS]
    if publisher is not None:
        publisher.publish(
            SkillLoaded(
                qualified_name=skill.qualified_name,
                revision=page.revision,
                mode="implicit",
                next_offset=page.next_offset,
            )
        )
    return prompt


def is_game_task(task: str) -> bool:
    """İstek bir tarayıcı oyunu mu (html-oyun becerisinin kuralıyla aynı karar)?"""
    kural = next(k for k in _RULES if k.skill == "html-oyun")
    if kural.pattern.search(task) is None:
        return False
    return kural.exclude is None or kural.exclude.search(task) is None


# Ölçüldü (30 Ekim, A1-32): "arka plan" (CSS), "window" (window.onload), "terminal",
# "web uygulaması" sıradan kod/web görevinde masaüstü araçlarını açıyordu. Yalnız
# masaüstü bağlamını gerçekten taşıyan kalıplar kaldı.
_DESKTOP_TASK = re.compile(
    r"masa(ü|u)st(ü|u)|pencere\b|arka\s*plan(da|daki)?\s+(?:uygulama|pencere|app|window)"
    r"|finder|safari|takvim|notlar\b"
    r"|(?<!web )(?<!mobil )(?<!mobile )uygulama(y(ı|i)|s(ı|i)(n(ı|i))?)?\b"
    r"|\bdesktop\b|background app|bilgisayar(ım|im)?da|ekran(ı|i)?mda"
    r"|chatgpt|codex|claude|slack|whatsapp|telegram|spotify|vs\s*code|xcode|figma|canva"
    r"|\bmail\b|chrome|tarayıcı",
    re.IGNORECASE,
)


# Yalnız yerel pencereyi hedefleyen araç adlarını, doğrudan eylem isteğinde tanı.
_NATIVE_WINDOW_TOOL = r"desktop_(?:window_focus|background_(?:windows|inspect|screenshot|action))"
_NATIVE_TOOL_REQUEST = re.compile(
    rf"^(?:please\s+)?(?:use|call|run)\s+(?:the\s+)?{_NATIVE_WINDOW_TOOL}(?![\w.-])"
    rf"|(?<![\w.-]){_NATIVE_WINDOW_TOOL}\s+"
    r"(?:(?:aracini\s+)?(?:press\s+)?(?:kullan|cagir|calistir)"
    r"|ile\s+[^.!?;\n]+\b(?:al|incele|listele|odakla|dogrula))"
    r"\s*(?:lutfen)?$"
)
_DESKTOP_REQUEST_LITERAL = re.compile(
    rf"```.*?(?:```|\Z)|`(?P<tool>{_NATIVE_WINDOW_TOOL})`|`[^`\n]*`|"
    r'"[^"\n]*"|“[^”\n]*”|‘[^’\n]*’|'
    r"(?<!\w)'[^'\n]+'(?!\w)|^[ \t]*>[^\n]*",
    re.S | re.M | re.I,
)
_DESKTOP_REQUEST_META = re.compile(
    r"^\s*(?:if|eger|explain|acikla|what|nedir)\b"
    r"|\b(?:ornek\w*|example\w*|varsayalim|suppose|demedim|demiyorum|instead of)\b"
)
_CALCULATOR_APP = re.compile(
    r"\b(?:hesap makinesi|calculator)\s+uygulamasinda\b"
    r"|\b(?:in|on|use|using)\s+(?:the\s+)?calculator app\b"
)
_CALCULATOR_BUTTON_REQUEST = re.compile(
    r"\bdugme(?:ye|lere)\s+(?:tikla|bas)\s*$"
    r"|^(?:please\s+)?(?:click|press)\s+(?:(?:the|only|visible)\s+)*buttons?\b"
)
_CALCULATOR_NON_NATIVE = re.compile(r"\b(?:web|browser|mobile|mobil|android|ios|python)\b")
_CALCULATOR_BUILD = re.compile(
    r"\b(?:hesap makinesi|calculator)\s+uygulamas[ıi](?:n[ıi])?\s+"
    r"(?:geli[şs]tir|olu[şs]tur|kodla|tasarla|yaz)\b",
    re.IGNORECASE,
)


def has_native_desktop_request(task: str) -> bool:
    """Doğrudan pencere aracı veya Hesap Makinesi düğmesi isteğini tanı."""
    prose = _DESKTOP_REQUEST_LITERAL.sub(lambda match: match["tool"] or " ", task)
    prose = fold_tr(prose).translate(str.maketrans("çğıöşü", "cgiosu"))
    clauses = [
        clause.strip()
        for clause in re.split(r"[.!?;]+(?=\s|$)|\n+", prose)
        if not _DESKTOP_REQUEST_META.search(clause)
    ]
    if any(_NATIVE_TOOL_REQUEST.search(clause) for clause in clauses):
        return True
    # İstek düğme yöntemini ve uygulamayı ayrı cümlelerde de söyleyebilir.
    calculator_clauses = [clause for clause in clauses if not _CALCULATOR_NON_NATIVE.search(clause)]
    return any(_CALCULATOR_APP.search(clause) for clause in calculator_clauses) and any(
        _CALCULATOR_BUTTON_REQUEST.search(clause) for clause in calculator_clauses
    )


def is_desktop_task(task: str) -> bool:
    """İstek masaüstü penceresi/uygulaması üzerinde mi (arka plan araçlarını açar)?"""
    return has_native_desktop_request(task) or (
        _DESKTOP_TASK.search(_CALCULATOR_BUILD.sub(" ", task)) is not None
    )


_WORKTREE_TASK = re.compile(
    r"worktree|çalışma\s+ağac|calisma\s+agac|izole\s+(?:bir\s+)?dal|ayrı\s+(?:bir\s+)?dal(?:da)?\b"
    r"|ana\s+(?:projeye|depoya)\s+dokunma",
    re.IGNORECASE,
)


def is_worktree_task(task: str) -> bool:
    """İstek izole git çalışma ağacı istiyor mu (enter/exit_worktree araçlarını açar)?

    Ölçüldü (31 Ekim): iki aracın şeması her istekte emülasyon istemini 11.400 karakterlik
    bütçenin üstüne çıkarıyordu; `SCOPED_TOOLS` deseniyle yalnız ilgili istekte sunulur.
    """
    return _WORKTREE_TASK.search(task) is not None


def is_remotion_task(task: str) -> bool:
    """İstek bir Remotion videosu mu (remotion-video becerisinin kuralıyla aynı karar)?"""
    kural = next(k for k in _RULES if k.skill == "remotion-video")
    return kural.pattern.search(task) is not None
