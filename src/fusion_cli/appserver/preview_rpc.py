"""Önizleme paneli RPC'leri (`onizleme.*`): launch.json, konsol/ağ günlüğü, ekran görüntüsü.

Ölçüldü (31 Ekim, P-041): panel yalnız kullanıcının yazdığı localhost adresini gömebiliyor,
sunucuyu uygulamadan başlatamıyor, konsolu/ağı okuyamıyor, görüntü alamıyordu. Buradaki
istekler `tools.preview_launch` ve `tools.preview_log` üzerine ince sarmalayıcıdır; adres
denetimi `web_preview.is_local_preview_url` ile aynıdır (panelin gömdüğü küme).
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Any

from ..tools import preview_launch
from ..tools.preview_launch import LaunchConfig, LaunchConfigError, LaunchUntrustedError
from ..tools.preview_log import (
    COLOR_SCHEMES,
    CaptureOptions,
    PageLog,
    clamp_settle,
    clamp_viewport,
    collect_page_log,
    save_screenshot,
)
from ..tools.preview_server import PreviewError
from .launch_autoverify import RPC_AUTO_VERIFY, set_auto_verify
from .web_preview import is_local_preview_url

RPC_CONFIGS = "onizleme.yapilandirmalar"
RPC_START = "onizleme.baslat"
RPC_STOP = "onizleme.durdur"
RPC_LOG = "onizleme.gunluk"
RPC_SCREENSHOT = "onizleme.ekran_goruntusu"
#: Okunan launch.json'un şu anki içeriğine güven (kullanıcı komutu panelde görüp onaylar).
RPC_TRUST = "onizleme.guven"
PREVIEW_RPC_NAMES = frozenset(
    {RPC_CONFIGS, RPC_START, RPC_STOP, RPC_LOG, RPC_SCREENSHOT, RPC_TRUST, RPC_AUTO_VERIFY}
)
#: Aynı anda tek ekran görüntüsü: her istek bir Chromium açar ve aynı dosyaya yazar. Ölçüldü
#: (31 Ekim): 320→375→768 hızlı geçişte geç biten 320 isteği dosyayı sonradan eziyordu.
_SCREENSHOT_LOCK = asyncio.Lock()

_NOT_LOCAL = "Yalnız localhost adresleri okunabilir."
_NAME_REQUIRED = "Yapılandırma adı (`ad`) gerekir."


def _error(message: str) -> dict[str, Any]:
    return {"ok": False, "metin": message}


def _config_payload(root: Path, config: LaunchConfig) -> dict[str, Any]:
    running = preview_launch.running_launch(root, config.name)
    return {
        "ad": config.name,
        "komut": config.command_text,
        "port": config.port,
        "url": config.address,
        "cwd": config.cwd,
        "baglan": config.is_attach,
        "calisiyor": running is not None,
        "guven_gerekli": config.needs_trust,
    }


def list_configs(root: Path) -> dict[str, Any]:
    try:
        loaded = preview_launch.load_launch_configs(root)
    except LaunchConfigError as error:
        return {**_error(str(error)), "dosya": preview_launch.LAUNCH_FILE, "yapilandirmalar": []}
    return {
        "ok": True,
        "kaynak": loaded.source,
        "dosya": preview_launch.LAUNCH_FILE,
        "guvenli": loaded.trusted,
        "uyarilar": list(loaded.warnings),
        # Browser ⋮ › Auto-verify changes (#439): üst düzey `autoVerify`.
        "otomatik_dogrulama": loaded.auto_verify,
        "yapilandirmalar": [_config_payload(root, config) for config in loaded.configs],
    }


async def start_config(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    name = data.get("ad")
    if not isinstance(name, str) or not name.strip():
        return _error(_NAME_REQUIRED)
    try:
        config = await asyncio.to_thread(preview_launch.find_launch_config, root, name.strip())
        preview = await preview_launch.start_launch(root, config)
    except LaunchUntrustedError as error:
        return {**_error(str(error)), "guven_gerekli": True, "komut": config.command_text}
    except (LaunchConfigError, PreviewError) as error:
        return _error(str(error))
    return {
        "ok": True,
        "ad": config.name,
        "url": preview.url,
        "komut": config.command_text,
        "not": preview_launch.port_note(config, preview),
    }


def trust_config_file(root: Path) -> dict[str, Any]:
    """Panelden "Güven ve başlat": okunan launch.json'un şu anki karmasını güvene al."""
    dosya = preview_launch.trust_launch_file(root)
    if dosya is None:
        return _error(f"{preview_launch.LAUNCH_FILE} yok; güvenilecek dosya bulunamadı.")
    return {"ok": True, "dosya": dosya}


def stop_config(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    name = data.get("ad")
    if not isinstance(name, str) or not name.strip():
        return _error(_NAME_REQUIRED)
    stopped = preview_launch.stop_launch(root, name.strip())
    return {"ok": True, "ad": name.strip(), "durduruldu": stopped}


def log_payload(log: PageLog) -> dict[str, Any]:
    return {
        "ok": not log.error,
        "url": log.url,
        "metin": log.error,
        "konsol": [
            {"seviye": entry.level, "metin": entry.text, "kaynak": entry.source}
            for entry in log.console
        ],
        "ag": [
            {
                "yontem": entry.method,
                "url": entry.url,
                "durum": entry.status,
                "tur": entry.resource_type,
                "hata": entry.failure,
                "basarisiz": entry.is_failed,
            }
            for entry in log.requests
        ],
        "hata_sayisi": log.error_count,
        "basarisiz_istek": len(log.failed_requests),
    }


async def page_log(data: dict[str, Any]) -> dict[str, Any]:
    url = data.get("url")
    if not is_local_preview_url(url):
        return _error(_NOT_LOCAL)
    options = CaptureOptions(
        viewport=clamp_viewport(data.get("genislik"), data.get("yukseklik")),
        settle_ms=clamp_settle(data.get("bekle_ms")),
    )
    return log_payload(await collect_page_log(str(url), options))


async def screenshot(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    url = data.get("url")
    if not is_local_preview_url(url):
        return _error(_NOT_LOCAL)
    scheme = data.get("tema")
    options = CaptureOptions(
        viewport=clamp_viewport(data.get("genislik"), data.get("yukseklik")),
        settle_ms=clamp_settle(data.get("bekle_ms")),
        screenshot=True,
        full_page=bool(data.get("tam_sayfa")),
        color_scheme=scheme if isinstance(scheme, str) and scheme in COLOR_SCHEMES else None,
    )
    async with _SCREENSHOT_LOCK:
        log = await collect_page_log(str(url), options)
        if log.error or log.screenshot is None:
            return _error(log.error or "Ekran görüntüsü alınamadı.")
        yol = await asyncio.to_thread(save_screenshot, root, log.screenshot)
    return {
        "ok": True,
        "url": log.url,
        "yol": yol,
        "mime": "image/png",
        "base64": base64.b64encode(log.screenshot).decode("ascii"),
        "genislik": options.viewport[0],
        "yukseklik": options.viewport[1],
        "hata_sayisi": log.error_count,
    }


async def handle_preview_rpc(root: Path, name: str, data: dict[str, Any]) -> dict[str, Any]:
    """`onizleme.*` isteğini yönlendir; bilinmeyen ad `ok=False`."""
    if name == RPC_CONFIGS:
        return await asyncio.to_thread(list_configs, root)
    if name == RPC_START:
        return await start_config(root, data)
    if name == RPC_STOP:
        return stop_config(root, data)
    if name == RPC_LOG:
        return await page_log(data)
    if name == RPC_SCREENSHOT:
        return await screenshot(root, data)
    if name == RPC_TRUST:
        return await asyncio.to_thread(trust_config_file, root)
    if name == RPC_AUTO_VERIFY:
        return await asyncio.to_thread(set_auto_verify, root, data)
    return _error(f"Bilinmeyen önizleme isteği: {name}")
