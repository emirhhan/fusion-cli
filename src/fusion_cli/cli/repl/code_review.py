"""`/code-review` (takma ad `/review`, #214) — Claude Code yerel inceleme komutu.

Sözdizimi Claude Code ile aynıdır: `[low|medium|high|xhigh|max|ultra] [--fix] [--comment]
[--max-findings n|all|default] [pr#|branch|path]`. Seviye ve bayraklardan sonra kalan metin
inceleme hedefidir (PR numarası, dal, yol ya da git aralığı); hedef yoksa dalın üst dala
göre önde olan commit'leri ve commit'lenmemiş değişiklikler incelenir.

Seviye yazılmazsa son yazılan `low`–`max` seviyesi yeniden kullanılır (önceki oturumdan da);
hiç yazılmadıysa oturumun effort ayarı geçerlidir. `--max-findings` değeri de `default`
verilene kadar hatırlanır. İnceleme ana bağlamı devralan fork alt ajanda koşar (Claude
Code'da arka plan alt ajanı). `ultra` Claude Code'un bulut incelemesidir; Fusion'da bulut
yoktur, kullanıcıya açıkça söylenir.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from ...ui import messages

_LOG = logging.getLogger(__name__)

LEVELS = ("low", "medium", "high", "xhigh", "max")
ULTRA = "ultra"
STATE_FILE = "code-review.json"
USAGE = (
    "Kullanım: /code-review [low|medium|high|xhigh|max|ultra] [--fix] [--comment] "
    "[--max-findings n|all|default] [pr#|branch|path]"
)


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    level: str | None
    fix: bool
    comment: bool
    #: `None` = belirtilmedi, `"default"` = hatırlananı sil, `"all"` ya da sayı.
    max_findings: str | None
    target: str
    ultra: bool = False


def parse(argument: str) -> ReviewRequest | str:
    """Argümanları ayrıştır; hata varsa kullanıcıya gösterilecek metin döner."""
    words = argument.split()
    level: str | None = None
    fix = comment = ultra = False
    max_findings: str | None = None
    index = 0
    if words and words[0].lower() in (*LEVELS, ULTRA):
        level = words[0].lower()
        ultra = level == ULTRA
        index = 1
    while index < len(words) and words[index].startswith("--"):
        flag = words[index]
        if flag == "--fix":
            fix = True
        elif flag == "--comment":
            comment = True
        elif flag == "--max-findings":
            if index + 1 >= len(words) or not _valid_max(words[index + 1]):
                return USAGE
            max_findings = words[index + 1].lower()
            index += 1
        elif flag == "--post" and ultra:
            pass  # Yalnız bulut incelemesinde anlamlı; Fusion'da bulut yok.
        else:
            return USAGE
        index += 1
    target = " ".join(words[index:])
    return ReviewRequest(level, fix, comment, max_findings, target, ultra)


def _valid_max(value: str) -> bool:
    return value.lower() in ("all", "default") or (value.isdigit() and int(value) > 0)


def _state_path(memory_dir: Path) -> Path:
    return memory_dir / STATE_FILE


def load_remembered(memory_dir: Path) -> dict[str, str]:
    try:
        data = json.loads(_state_path(memory_dir).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        _LOG.debug("code-review durumu okunamadı: %s", error)
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str)} if isinstance(data, dict) else {}


def remember(memory_dir: Path, request: ReviewRequest) -> dict[str, str]:
    """Yazılan seviyeyi ve `--max-findings`'i hatırla; güncel kaydı döndür."""
    current = load_remembered(memory_dir)
    updated = dict(current)
    if request.level in LEVELS:
        updated["level"] = request.level
    if request.max_findings == "default":
        updated.pop("max_findings", None)
    elif request.max_findings is not None:
        updated["max_findings"] = request.max_findings
    if updated != current:
        try:
            memory_dir.mkdir(parents=True, exist_ok=True)
            _state_path(memory_dir).write_text(json.dumps(updated), encoding="utf-8")
        except OSError as error:
            _LOG.warning("code-review durumu yazılamadı: %s", error)
    return updated


def build_task(request: ReviewRequest, level: str, max_findings: str | None) -> str:
    """Fork alt ajana verilecek inceleme görevi."""
    scope = (
        messages.CODE_REVIEW_TARGET.format(target=request.target)
        if request.target
        else messages.CODE_REVIEW_DEFAULT_SCOPE
    )
    parts = [messages.CODE_REVIEW_TASK.format(scope=scope)]
    parts.append(messages.CODE_REVIEW_LOW if level == "low" else messages.CODE_REVIEW_BROAD)
    if level in ("xhigh", "max"):
        parts.append(messages.CODE_REVIEW_CLEANUPS)
    if max_findings == "all":
        parts.append(messages.CODE_REVIEW_ALL_FINDINGS)
    elif max_findings is not None:
        parts.append(messages.CODE_REVIEW_MAX_FINDINGS.format(count=max_findings))
    parts.append(messages.CODE_REVIEW_FIX if request.fix else messages.CODE_REVIEW_REPORT_ONLY)
    if request.comment:
        parts.append(messages.CODE_REVIEW_COMMENT)
    return "\n".join(parts)
