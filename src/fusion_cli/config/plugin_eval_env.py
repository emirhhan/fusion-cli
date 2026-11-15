"""`fusion plugin eval` alt sürecine ortamdan geçen ayarlar (Claude Code `plugin eval`, #380).

Eval her koşuyu ayrı bir `fusion agent` alt sürecinde yürütür; `--model`/`--judge-model` ve MCP
sahte sunucuları (`--mocks`) o sürecin yapılandırmasına yalnız şu ortam değişkenleriyle girer:

- `FUSION_EVAL_MODEL`: ana ajan modeli (aday adı ya da model kimliği).
- `FUSION_EVAL_MCP`: JSON `{"mode": "record"|"off", "allow_real": bool,
  "mocks": {<sunucu>: <klasör>}}`.
  `record`: sahtesi olan eklenti sunucusu yerine sahte sunucu başlar; sahtesi olmayan eklenti
  sunucusu `allow_real` (Claude `--allow-real-servers`) yoksa hiç başlamaz. `off`: değişiklik yok.

Değişkenler yoksa yapılandırma aynen döner; kullanıcı oturumunu etkilemez.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import sys

from ..core.types import ModelSpec
from .models import Config, McpServerConfig, McpTransport

_LOG = logging.getLogger(__name__)

MODEL_ENV = "FUSION_EVAL_MODEL"
MCP_ENV = "FUSION_EVAL_MCP"
MOCK_MODULE = "fusion_cli.tools.plugin_eval_mock_server"


def _model_spec(config: Config, wanted: str) -> ModelSpec:
    for spec in config.candidates:
        if wanted in {spec.name, spec.model}:
            return spec
    return config.agent.with_identity(wanted)


def with_eval_model(config: Config) -> Config:
    """`FUSION_EVAL_MODEL` verildiyse ana ajan o model olur (Claude `--model`)."""
    wanted = os.environ.get(MODEL_ENV, "").strip()
    if not wanted:
        return config
    return dataclasses.replace(config, agent=_model_spec(config, wanted))


def server_key(name: str) -> str:
    """`plugin:<eklenti>:<sunucu>` → `<sunucu>` (sahte klasörü `.mcp.json` anahtarıdır)."""
    return name.rsplit(":", 1)[-1]


def _settings() -> dict[str, object] | None:
    raw = os.environ.get(MCP_ENV, "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        _LOG.warning("%s okunamadı; eklenti MCP sunucuları başlatılmıyor", MCP_ENV)
        return {"mode": "record", "allow_real": False, "mocks": {}}
    return data if isinstance(data, dict) else None


def with_eval_mocks(servers: tuple[McpServerConfig, ...]) -> tuple[McpServerConfig, ...]:
    """Eval alt sürecinde eklenti MCP sunucularını sahteleriyle değiştir ya da başlatma."""
    settings = _settings()
    if settings is None or settings.get("mode") == "off":
        return servers
    mocks = settings.get("mocks")
    folders = mocks if isinstance(mocks, dict) else {}
    allow_real = settings.get("allow_real") is True
    kept: list[McpServerConfig] = []
    for server in servers:
        folder = folders.get(server_key(server.name))
        if isinstance(folder, str) and folder:
            kept.append(
                dataclasses.replace(
                    server,
                    command=sys.executable,
                    args=("-m", MOCK_MODULE, folder),
                    transport=McpTransport.STDIO,
                    url="",
                    env_names=(),
                    token_env="",
                )
            )
        elif allow_real:
            kept.append(server)
    return tuple(kept)
