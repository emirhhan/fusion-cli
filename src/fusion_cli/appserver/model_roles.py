"""Modeller sekmesi — rol başına model seçimi (varsayılan, öğretmen, Fusion modu).

Kullanıcı `config.yaml` düzenlemek zorunda kalmasın diye roller panelden atanır ve
kalıcı yazılır. Roller:

- `agent`      : varsayılan (ajan) modeli
- `teacher`    : `ask_teacher`'ın danıştığı model; boş = otomatik
- `judge`      : Fusion modunun hakemi
- `candidates` : Fusion modunun aday havuzu
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

from ..config import writer
from ..config.model_select import set_agent_model, set_judge_model
from ..config.models import Config
from ..core.errors import ConfigError
from ..core.types import ModelSpec
from ..providers.codex_cli import PREFIX as CODEX_PREFIX
from ..providers.codex_cli import codex_ready
from .model_catalog import list_selectable_models

ROLES = ("agent", "teacher", "judge", "candidates", "codex_yedek", "web_yedek")


def _current(config: Config) -> dict[str, Any]:
    return {
        "agent": config.agent.model,
        "teacher": config.teacher.model if config.teacher is not None else "",
        "judge": config.judge.model,
        "candidates": [spec.model for spec in config.candidates],
        "codex_yedek": config.runtime.teacher_codex_fallback,
        "web_yedek": config.runtime.auto_web_fallback,
    }


def _web_rows(config: Config) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for session in config.web_sessions:
        if not session.enabled:
            continue
        name = session.provider.removesuffix("_web").title()
        rows.append(
            {
                "model": session.model,
                "etiket": f"{name} · {session.selected_model or 'otomatik'} ({session.account})",
                "grup": "Web oturumları",
                "hazir": session.login_verified,
                "not": "" if session.login_verified else "giriş doğrulanmadı",
            }
        )
    return rows


def _codex_row() -> dict[str, Any]:
    ready = codex_ready()
    return {
        "model": f"{CODEX_PREFIX}default",
        "etiket": "ChatGPT · Codex (KODLAMA limitini harcar)",
        "grup": "Abonelik",
        "hazir": ready,
        "not": "" if ready else "terminalde `codex login` gerekir",
        # Codex düz metin üretir; araç çağıramaz, bu yüzden ajan rolüne atanamaz.
        "arac": False,
    }


async def role_state(config: Config) -> dict[str, Any]:
    """Seçili roller ve seçilebilir modeller."""
    options = [*_web_rows(config), _codex_row()]
    seen = {row["model"] for row in options}
    try:
        catalog = await list_selectable_models(config, workspace_mode="sohbet")
    except Exception:
        catalog = {"modeller": []}
    for row in catalog.get("modeller", []):
        if row["model"] in seen:
            continue
        seen.add(row["model"])
        options.append(
            {
                "model": row["model"],
                "etiket": row.get("etiket") or row["model"],
                "grup": "API / yerel",
                "hazir": True,
                "not": "",
            }
        )
    current = _current(config)
    for model in (current["agent"], current["judge"], *current["candidates"]):
        if model and model not in seen:
            seen.add(model)
            options.append(
                {"model": model, "etiket": model, "grup": "Ayarlı", "hazir": True, "not": ""}
            )
    sessions = [
        {
            "saglayici": session.provider,
            "hesap": session.account,
            "etiket": f"{session.provider.removesuffix('_web').title()} ({session.account})",
            "dogrulandi": session.login_verified,
        }
        for session in config.web_sessions
        if session.enabled
    ]
    return {"ok": True, "roller": current, "secenekler": options, "oturumlar": sessions}


def _validated(model: object) -> str:
    text = model.strip() if isinstance(model, str) else ""
    if "/" not in text:
        raise ConfigError(f"Geçersiz model kimliği: {text!r} (biçim: sağlayıcı/model).")
    return text


def apply_role(config: Config, role: str, value: object) -> Config:
    """Rolü ata ve kalıcı yaz; yeni yapılandırmayı döndür."""
    if role == "agent":
        if isinstance(value, str) and value.startswith(CODEX_PREFIX):
            raise ConfigError(
                "Codex araç çağıramaz; varsayılan (ajan) model olamaz. "
                "Öğretmen, hakem veya Fusion adayı olarak seç."
            )
        new = set_agent_model(config, _validated(value))
        writer.write_model_section(new)
    elif role == "judge":
        new = set_judge_model(config, _validated(value))
        writer.write_model_section(new)
    elif role == "teacher":
        model = value.strip() if isinstance(value, str) else ""
        teacher = ModelSpec(name="ogretmen", model=_validated(model)) if model else None
        new = replace(config, teacher=teacher)
        writer.write_teacher(new)
    elif role == "candidates":
        models = [_validated(item) for item in value] if isinstance(value, list) else []
        if not models:
            raise ConfigError("Fusion modu için en az bir aday modeli seç.")
        specs = tuple(
            ModelSpec(name=f"aday-{index + 1}", model=model, tags=("strict",))
            for index, model in enumerate(dict.fromkeys(models))
        )
        new = replace(
            config,
            candidates=specs,
            task_model_map=dict.fromkeys(config.task_model_map, specs[0].name),
        )
        writer.write_model_section(new)
    elif role == "codex_yedek":
        enabled = value is True
        new = replace(config, runtime=replace(config.runtime, teacher_codex_fallback=enabled))
        writer.write_runtime_flag(new, "teacher_codex_fallback", enabled)
    elif role == "web_yedek":
        enabled = value is True
        new = replace(config, runtime=replace(config.runtime, auto_web_fallback=enabled))
        writer.write_runtime_flag(new, "auto_web_fallback", enabled)
    else:
        raise ConfigError(f"Bilinmeyen rol: {role!r}. Geçerli: {', '.join(ROLES)}")
    return new


async def assign(config: Config, role: str, value: object) -> tuple[Config | None, dict[str, Any]]:
    try:
        new = await asyncio.to_thread(apply_role, config, role, value)
    except ConfigError as error:
        return None, {"ok": False, "metin": str(error)}
    return new, {"ok": True, "metin": "Kaydedildi.", "roller": _current(new)}
