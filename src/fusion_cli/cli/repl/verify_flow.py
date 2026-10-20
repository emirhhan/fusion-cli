"""`/verify` akışı — doğrulama kapısını keşfet, onaylat, kalıcılaştır.

Kapı OPT-IN kalır ama artık kullanıcının komutları elle yazmasını beklemez: plan
projeden çıkarılır, ekranda GÖSTERİLİR ve ancak onaylanırsa yazılır.

Otomatik açmıyoruz. Keşif tahmindir; yanlış bir tahmin (kurulu olmayan bir araç,
başka amaçla yazılmış bir make hedefi) kapıyı her turda düşürür ve agent gerçek
olmayan bir hatayı düzeltmeye çalışır. Kullanıcının bir kez bakması bu riski
tamamen ortadan kaldırır.

Seçim ekranı dışarıdan geçirilir: canlı terminale bakar, enjekte edilmeseydi bu
akış ancak gerçek bir TTY ile test edilebilirdi (bkz. `model_flows`).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ...config import writer
from ...config.models import Config
from ...core.errors import ConfigError
from ...engines.agent.verify_discovery import discover_commands
from ...ui import messages
from ...ui.picker import Choice, pick
from .model_flows import FlowResult, Picker


def choose_verification(
    config: Config, root: Path, *, picker: Picker = pick, discover: object = None
) -> FlowResult:
    """Doğrulama planını keşfet, onaylat ve kaydet.

    Kapı zaten kuruluysa hiçbir şey sorulmaz: kullanıcının kendi yazdığı komutları
    bir keşif tahminiyle ezmek, üzerine düşünülmüş bir yapılandırmayı sessizce
    bozmak olurdu.
    """
    if config.runtime.verification_commands:
        return FlowResult(config, messages.VERIFY_ACTIVE.format(commands=_liste(config)))

    kesfet = discover if callable(discover) else discover_commands
    plan: tuple[str, ...] = tuple(kesfet(root))
    if not plan:
        return FlowResult(config, messages.VERIFY_NOTHING_FOUND)

    if not _onaylandi(plan, picker):
        return FlowResult(config, messages.PICKER_CANCELLED)

    updated = replace(config, runtime=replace(config.runtime, verification_commands=plan))
    applied = messages.VERIFY_APPLIED.format(commands=_bicimlendir(plan))
    return FlowResult(updated, f"{applied}\n{_persist(updated, plan)}")


def _onaylandi(plan: tuple[str, ...], picker: Picker) -> bool:
    """Planı göster ve tek bir evet/hayır al."""
    baslik = f"{messages.VERIFY_PLAN_HEADING}\n{_bicimlendir(plan)}\n\n{messages.VERIFY_TITLE}"
    secim = picker(
        (
            Choice("evet", messages.VERIFY_ACCEPT, messages.VERIFY_ACCEPT_HINT),
            Choice("hayir", messages.VERIFY_REJECT, messages.VERIFY_REJECT_HINT),
        ),
        title=baslik,
    )
    return secim == "evet"


def _bicimlendir(commands: tuple[str, ...]) -> str:
    return "\n".join(f"  {index}. {command}" for index, command in enumerate(commands, 1))


def _liste(config: Config) -> str:
    return _bicimlendir(config.runtime.verification_commands)


def _persist(config: Config, plan: tuple[str, ...]) -> str:
    """Planı kalıcılaştır. Yazamamak akışı bozmaz, yalnızca bildirilir."""
    try:
        return messages.LEVEL_SAVED.format(path=writer.write_verification_commands(config, plan))
    except ConfigError as error:
        return messages.VERIFY_SAVE_FAILED.format(error=error)
