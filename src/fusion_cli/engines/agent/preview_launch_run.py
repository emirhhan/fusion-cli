"""`start_preview name=…`: `.fusion/launch.json` yapılandırmasını başlat ve sayfayı ölç.

`preview_tools.run_preview` dosyalardan anlaşılan türleri çalıştırır; burası kullanıcının
ADLANDIRDIĞI sunucuyu (monorepo, özel port, çalışana bağlanma) aynı sonuç biçimiyle
açar. Ölçüm (`probe`) ve `PreviewReady` yayını `run_preview` ile aynıdır ki masaüstü
paneli ve kapanış kapısı iki yolu ayırt etmesin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urljoin

from ...core.events import PreviewReady
from ...core.tool_content import ToolContent
from ...core.tools import ToolResult
from ...tools import preview_launch
from ...tools.preview_launch import LaunchConfigError, LaunchConfigs
from ...tools.preview_probe import probe
from ...tools.preview_server import PreviewError, PreviewKind

if TYPE_CHECKING:
    from pathlib import Path

    from .loop import AgentDeps


def launch_hint(root: Path) -> str:
    """Tür anlaşılmadığında modele gidecek ek: launch.json varsa adlarını say."""
    try:
        loaded: LaunchConfigs = preview_launch.load_launch_configs(root)
    except LaunchConfigError as error:
        return f" {error}"
    if not loaded.configs:
        return ""
    adlar = ", ".join(f"'{config.name}'" for config in loaded.configs)
    return (
        f" {loaded.source} içinde tanımlı sunucular: {adlar} — start_preview'ı name='…' ile çağır."
    )


async def run_launch_preview(deps: AgentDeps, root: Path, name: str, page: object) -> ToolResult:
    try:
        config = preview_launch.find_launch_config(root, name)
        preview = await preview_launch.start_launch(root, config)
    except (LaunchConfigError, PreviewError) as error:
        return ToolResult.failure(f"Önizleme başlatılamadı: {error}")
    url = preview.url
    if isinstance(page, str) and page.strip():
        url = urljoin(preview.url, page.strip())
    sonuc = await probe(url)
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
