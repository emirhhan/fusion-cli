"""`start_preview name=…`: `.claude/launch.json` yapılandırmasını başlat ve sayfayı ölç.

`preview_tools.run_preview` dosyalardan anlaşılan türleri çalıştırır; burası kullanıcının
ADLANDIRDIĞI sunucuyu (monorepo, özel port, çalışana bağlanma) aynı sonuç biçimiyle
açar. Ölçüm (`probe`) ve `PreviewReady` yayını `run_preview` ile aynıdır ki masaüstü
paneli ve kapanış kapısı iki yolu ayırt etmesin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...core.events import PreviewReady
from ...core.tool_content import ToolContent
from ...core.tools import ToolResult
from ...tools import preview_launch
from ...tools.preview_launch import LaunchConfigError, LaunchConfigs, join_local_page
from ...tools.preview_probe import probe
from ...tools.preview_server import PreviewError, PreviewKind

if TYPE_CHECKING:
    from pathlib import Path

    from .loop import AgentDeps


def launch_hint(root: Path) -> str:
    """Tür anlaşılmadığında modele gidecek ek: launch.json varsa adlarını say.

    Güvenilmeyen dosyadaki komutlu yapılandırmalar ÖNERİLMEZ: model çağırsa da çalışmaz;
    kullanıcıya `fusion trust` gerektiği söylenir. Yalnız `url` ile bağlananlar önerilir.
    """
    try:
        loaded: LaunchConfigs = preview_launch.load_launch_configs(root)
    except LaunchConfigError as error:
        return f" {error}"
    if not loaded.configs:
        return " " + " ".join(loaded.warnings) if loaded.warnings else ""
    kullanilabilir = [config for config in loaded.configs if not config.needs_trust]
    bekleyen = [config for config in loaded.configs if config.needs_trust]
    parcalar: list[str] = []
    if kullanilabilir:
        adlar = ", ".join(f"'{config.name}'" for config in kullanilabilir)
        parcalar.append(
            f"{loaded.source} içinde tanımlı sunucular: {adlar} — start_preview'ı name='…' ile "
            "çağır."
        )
    if bekleyen:
        adlar = ", ".join(f"'{config.name}'" for config in bekleyen)
        parcalar.append(
            f"{loaded.source} içindeki komutlu yapılandırmalar ({adlar}) bu proje güvenilmediği "
            "için çalıştırılmaz; kullanıcı `fusion trust` ile onaylamalı. Onay gelmeden "
            "start_preview'ı bu adlarla çağırma."
        )
    parcalar.extend(loaded.warnings)
    return " " + " ".join(parcalar)


async def run_launch_preview(deps: AgentDeps, root: Path, name: str, page: object) -> ToolResult:
    try:
        config = preview_launch.find_launch_config(root, name)
        preview = await preview_launch.start_launch(root, config)
        url = join_local_page(preview.url, page)
    except (LaunchConfigError, PreviewError) as error:
        return ToolResult.failure(f"Önizleme başlatılamadı: {error}")
    sonuc = await probe(url)
    # Kapanış kapısı (site_verify) adlı sunucuyu da buradan okur: ikinci bir geçici sunucu açmaz.
    preview.last_probe = {"ok": not sonuc.problems, "summary": sonuc.summary(), "url": url}
    if 0 < sonuc.status < 400:
        deps.publisher.publish(
            PreviewReady(url=url, kind=PreviewKind.LAUNCH.value, root=str(root), title=sonuc.title)
        )
    lines = [
        (
            f"Önizleme çalışıyor: {url} ('{config.name}' yapılandırması"
            + (
                f", komut: {config.command_text}"
                if not config.is_attach
                else ", çalışana bağlanıldı"
            )
            + "). Kullanıcı bu adresi açabilir."
            if 0 < sonuc.status < 400
            else f"BAŞARISIZ: HTTP {sonuc.status or 'yanıt yok'} ({url})"
        ),
        f"Ölçüm: {sonuc.summary()}.",
    ]
    if note := preview_launch.port_note(config, preview):
        lines.insert(1, note)
    problems = [*sonuc.problems, *(f"konsol hatası: {error}" for error in sonuc.console_errors[:5])]
    if problems:
        lines.append("SORUNLAR (düzelt ve start_preview'ı tekrar çağır):")
        lines.extend(f"- {problem}" for problem in problems)
    else:
        lines.append("Sayfa hatasız açıldı.")
    lines.append("Konsol ve ağ ayrıntısı için preview_console / preview_network.")
    content: tuple[ToolContent, ...] = ()
    if sonuc.screenshot:
        import base64

        content = (ToolContent.image("image/jpeg", base64.b64encode(sonuc.screenshot).decode()),)
    return ToolResult("\n".join(lines), ok=0 < sonuc.status < 400, content=content)
