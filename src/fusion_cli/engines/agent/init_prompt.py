"""`/init` görevi Claude Code ile birebir (#155).

Claude Code (code.claude.com/docs/en/memory, "Set up a project CLAUDE.md"): `/init` kod
tabanını inceleyip CLAUDE.md üretir (build/test komutları, proje kuralları); CLAUDE.md zaten
varsa üzerine yazmaz, iyileştirme önerir. `.cursor/rules`, `.cursorrules` ve
`.github/copilot-instructions.md` içeriğini katar. `CLAUDE_CODE_NEW_INIT=1` çok aşamalı akışı
açar: hangi yapıtların (CLAUDE.md, beceriler, kancalar) kurulacağını sorar, alt ajanla depoyu
inceler, eksikleri sorar ve yazmadan önce önerisini gösterir. Codex/Gemini yapılandırması
bulunursa `/import` önerilir.

Varsayılan hedef artık CLAUDE.md'dir; `agents` biçimi (AGENTS.md) bir sürüm boyunca seçilebilir.
Sabit bölüm listesi ve 3.000 karakter dayatması kaldırıldı (Claude'da yok).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

INIT_TARGETS: dict[str, str] = {"claude": "CLAUDE.md", "agents": "AGENTS.md"}
DEFAULT_INIT_FORMAT = "claude"

#: Claude'un /init'in kattığı diğer araçların kural dosyaları.
FOREIGN_RULES = (".cursor/rules", ".cursorrules", ".github/copilot-instructions.md")
#: Bulunursa `/import` önerilen yapılandırmalar (araç → işaret yolu).
IMPORTABLE = (("codex", "AGENTS.md"), ("codex", ".codex"), ("gemini", "GEMINI.md"))

NEW_INIT_ENV = "CLAUDE_CODE_NEW_INIT"


def target_for(fmt: str) -> str:
    """Biçim → hedef dosya; bilinmeyen biçim CLAUDE.md."""
    return INIT_TARGETS.get(fmt.strip().lower(), INIT_TARGETS[DEFAULT_INIT_FORMAT])


def foreign_rules(root: Path) -> tuple[str, ...]:
    """Depoda bulunan Cursor/Copilot kural yolları."""
    return tuple(rel for rel in FOREIGN_RULES if (root / rel).exists())


def import_hints(root: Path) -> tuple[str, ...]:
    """`/import <araç>` önerilecek araçlar (sıra korunur, tekrarsız)."""
    found: list[str] = []
    for tool, rel in IMPORTABLE:
        if (root / rel).exists() and tool not in found:
            found.append(tool)
    return tuple(found)


def _new_init_steps(target: str) -> str:
    return (
        "Çok aşamalı kurulum (CLAUDE_CODE_NEW_INIT=1): 1) `ask_user` ile hangi yapıtların "
        f"kurulacağını sor: `{target}`, beceriler (`.claude/skills/`), kancalar "
        "(`.claude/settings.json` hooks), kişisel `CLAUDE.local.md`. 2) Depoyu bir alt ajanla "
        "incele. 3) Koddan çıkarılamayan boşlukları `ask_user` ile sor. 4) Herhangi bir dosya "
        "yazmadan önce önerini incelenebilir biçimde göster ve onay al.\n"
    )


def init_task(
    root: Path,
    *,
    fmt: str = DEFAULT_INIT_FORMAT,
    facts: str = "",
    environ: Mapping[str, str] | None = None,
) -> str:
    """Modele verilecek `/init` görevi; `facts` Fusion'ın depodan ölçtükleridir."""
    env = os.environ if environ is None else environ
    target = target_for(fmt)
    parts = [
        f"Bu kod tabanını incele ve kökte bir `{target}` dosyası oluştur (Claude Code /init). "
        "Dosya gelecekteki oturumlara rehber olsun: derleme, test ve lint komutları (tek testi "
        "koşmak dahil), kodun okunmasıyla hemen anlaşılmayan büyük resim mimarisi ve bu depoya "
        "özgü kurallar. Genel geliştirme öğüdü ve kolayca keşfedilebilen dosya listeleri yazma; "
        "kısa ve somut tut. README ve paket dosyalarını oku.\n",
    ]
    if facts:
        parts.append(facts + "\n")
    rules = foreign_rules(root)
    if rules:
        parts.append(
            "Şu kural dosyaları var; önemli kısımlarını içeriğe kat: "
            + ", ".join(f"`{rel}`" for rel in rules)
            + ".\n"
        )
    hints = import_hints(root)
    if hints:
        parts.append(
            "Başka bir aracın yapılandırması bulundu; özetin sonunda kullanıcıya "
            + ", ".join(f"`/import {tool}`" for tool in hints)
            + " önermeyi unutma.\n"
        )
    if env.get(NEW_INIT_ENV, "").strip() in {"1", "true", "yes"}:
        parts.append(_new_init_steps(target))
    parts.append(
        f"`{target}` ZATEN VARSA üzerine yazma: neyin iyileştirilebileceğini öner ve `ask_user` "
        "ile onay al."
    )
    return "".join(parts)
