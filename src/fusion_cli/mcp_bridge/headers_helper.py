"""`headersHelper`: bağlantı anında JSON başlık sözlüğü üreten kabuk komutu (#249).

Claude Code kuralları (https://code.claude.com/docs/en/mcp — Use dynamic headers):
- Komut kabukta çalışır, 10 sn sonra bırakılır; stdout'a dizgi→dizgi JSON nesnesi yazmalıdır.
- Her bağlantıda yeniden çalışır (önbellek yok); dinamik başlıklar aynı adlı sabitleri ezer.
- Ortamda `CLAUDE_CODE_MCP_SERVER_NAME` ve `CLAUDE_CODE_MCP_SERVER_URL` vardır.
- Çalışma dizini: proje/yerel → proje kökü; kullanıcı → yapılandırma dizini.
- Proje (`.mcp.json`) ya da eklenti kaynaklı yardımcı, adı kimlik bilgisine benzeyen
  (TOKEN, SECRET, PASSWORD, KEY, AUTH) ortam değişkenleri çıkarılarak çalıştırılır.
- Yerel kapsamdaki yardımcı yalnız proje klasörüne güvenildiyse çalışır; yoksa sunucu
  yalnız sabit `headers` ile bağlanır.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import Mapping
from pathlib import Path

from ..config.models import McpScope, McpServerConfig
from ..core.env_refs import REMOTE_BLANKED_VARIABLES
from .types import McpConfigError

_LOG = logging.getLogger(__name__)

HELPER_TIMEOUT_S = 10.0
_CREDENTIAL_NAME = re.compile(r"TOKEN|SECRET|PASSWORD|KEY|AUTH", re.IGNORECASE)
_GIT_CONFIG_KEY = re.compile(r"^GIT_CONFIG_KEY_\d+$")


def helper_environment(
    config: McpServerConfig, environ: Mapping[str, str] | None = None
) -> dict[str, str]:
    source = dict(os.environ if environ is None else environ)
    if config.scope in (McpScope.PROJECT, McpScope.PLUGIN):
        source = {
            name: value
            for name, value in source.items()
            if _GIT_CONFIG_KEY.match(name)
            or not (_CREDENTIAL_NAME.search(name) or name in REMOTE_BLANKED_VARIABLES)
        }
    return {
        **source,
        "CLAUDE_CODE_MCP_SERVER_NAME": config.name,
        "CLAUDE_CODE_MCP_SERVER_URL": config.url,
    }


def helper_cwd(config: McpServerConfig, root: Path | None = None) -> Path:
    if config.scope in (McpScope.PROJECT, McpScope.LOCAL):
        return root or Path.cwd()
    from ..config.paths import user_config_dir

    directory = user_config_dir()
    return directory if directory.is_dir() else Path.home()


def helper_allowed(config: McpServerConfig, root: Path | None = None) -> bool:
    """Yerel kapsamda proje klasörü güvenilmeden yardımcı çalışmaz (proje `.mcp.json`
    zaten yalnız güvenilen dosyadan yüklenir)."""
    if config.scope is not McpScope.LOCAL:
        return True
    from ..config.trust import resolve_project_trust

    return resolve_project_trust(root or Path.cwd()).trusted


async def run_headers_helper(
    config: McpServerConfig, *, root: Path | None = None, environ: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Yardımcıyı çalıştır; başlık sözlüğünü döndür. Yardımcı yoksa boş."""
    if not config.headers_helper:
        return {}
    if not helper_allowed(config, root):
        _LOG.warning(
            "headersHelper çalıştırılmadı: %s için proje klasörü güvenilir değil (fusion trust)",
            config.name,
        )
        return {}
    process = await asyncio.create_subprocess_shell(
        config.headers_helper,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(helper_cwd(config, root)),
        env=helper_environment(config, environ),
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=HELPER_TIMEOUT_S)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise McpConfigError(
            f"{config.name}: headersHelper {HELPER_TIMEOUT_S:.0f} sn içinde bitmedi"
        ) from None
    if process.returncode != 0:
        raise McpConfigError(f"{config.name}: headersHelper {process.returncode} koduyla bitti")
    return parse_helper_output(config.name, stdout.decode("utf-8", errors="replace"))


def parse_helper_output(name: str, text: str) -> dict[str, str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise McpConfigError(f"{name}: headersHelper çıktısı JSON değil") from None
    if not isinstance(data, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in data.items()
    ):
        raise McpConfigError(f"{name}: headersHelper dizgi→dizgi JSON nesnesi yazmalı")
    return data


def has_authorization(headers: Mapping[str, str]) -> bool:
    """Başlıklarda Authorization varsa OAuth'a düşülmez (Claude Code)."""
    return any(key.lower() == "authorization" for key in headers)
