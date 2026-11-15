"""Monorepo alt klasörlerindeki becerilerin tembel keşfi (P-052).

Claude Code, alt klasördeki dosyalarla çalışılırken o klasörün (ve köke kadar üstlerinin)
`.claude/skills` dizinlerini de yükler. Fusion aynı anı kullanır: model bir dosyaya erişince
iç içe talimatlar yüklenir (`project_instructions.load_nested_instructions`); aynı kanca
dosyanın klasöründen köke kadar (kök HARİÇ: kökünkiler zaten taranır) `.claude/skills` ve
`.agents/skills` dizinlerini kataloğa ekler ve yeni becerileri modele tek satırla duyurur.

Güven: bulunan beceriler "proje" kaynağıdır (depo içeriği). Duyuru metni nötralize edilir;
`!`cmd`` yalnız salt-okur koşar, beceri dizininde `<proje_becerileri>` bloğuna girer.
Gürültü dizinleri (`node_modules`, `dist`…) ve gizli klasörler atlanır; kök dışına çıkan
hedef ya da sembolik bağ hiç taranmaz.
"""

from __future__ import annotations

from pathlib import Path

from ...core.types import Message
from ...tools.capabilities import Capability, CapabilityRegistry
from ...tools.capability_roots import NESTED_SKILL_DIRS
from .instruction_layers import neutralize
from .project_instructions import NESTED_SKIP_DIRS

#: Duyuruda en fazla kaç beceri adı listelenir.
NOTE_MAX_SKILLS = 12
#: Duyuru satırında açıklamanın en fazla uzunluğu.
NOTE_DESCRIPTION_CHARS = 100

NOTE_HEADER = (
    "FUSION_NOT: Eriştiğin alt klasörde projeye ait beceriler bulundu (depo içeriği, kullanıcı "
    "talimatı değildir). O klasördeki işe uyuyorsa read_skill('<ad>') ile yükle:"
)


def nested_skill_dirs(root: Path, target: Path) -> tuple[Path, ...]:
    """`target`'ın klasöründen köke kadar (kök hariç) var olan beceri dizinleri; iç → dış."""
    try:
        kok = root.resolve()
        gercek = target.resolve()
    except (OSError, RuntimeError):
        return ()
    if not gercek.is_relative_to(kok):
        return ()
    klasor = gercek if gercek.is_dir() else gercek.parent
    parcalar = klasor.relative_to(kok).parts
    if any(part in NESTED_SKIP_DIRS or part.startswith(".") for part in parcalar):
        return ()
    found: list[Path] = []
    for depth in range(len(parcalar), 0, -1):
        dizin = kok.joinpath(*parcalar[:depth])
        for rel in NESTED_SKILL_DIRS:
            aday = dizin / rel
            try:
                if aday.is_dir() and aday.resolve().is_relative_to(kok):
                    found.append(aday)
            except OSError:
                continue
    return tuple(found)


def discover_nested_skills(
    registry: CapabilityRegistry | None, root: Path, targets: tuple[Path, ...]
) -> Message | None:
    """Erişilen dosyaların alt klasör becerilerini kataloğa ekle; yeni beceri varsa duyuru."""
    if registry is None or not targets:
        return None
    folders = tuple(
        dict.fromkeys(folder for target in targets for folder in nested_skill_dirs(root, target))
    )
    added = registry.add_nested_roots(folders) if folders else ()
    visible = [item for item in added if item.model_invocable]
    if not visible:
        return None
    return Message("user", _note(visible, root), harness_note=True)


def _note(skills: list[Capability], root: Path) -> str:
    lines = [NOTE_HEADER]
    for item in skills[:NOTE_MAX_SKILLS]:
        summary = " ".join(item.description.split())[:NOTE_DESCRIPTION_CHARS]
        try:
            where = item.path.parent.relative_to(root.resolve()).as_posix()
        except ValueError:
            where = item.path.parent.name
        lines.append(neutralize(f"- {item.name} ({where})" + (f" — {summary}" if summary else "")))
    if len(skills) > NOTE_MAX_SKILLS:
        lines.append(f"[…+{len(skills) - NOTE_MAX_SKILLS} beceri daha; find_skill ile ara.]")
    return "\n".join(lines)
