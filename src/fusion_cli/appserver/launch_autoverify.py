"""Browser bölmesinin ⋮ › Auto-verify changes anahtarı (#439, #440).

Claude Code Desktop: ⋮ menüsündeki "Auto-verify changes" projenin `.claude/launch.json`
dosyasındaki üst düzey `autoVerify` değerini değiştirir. Dosya yorum içeriyorsa üzerine
yazılmaz (yorumlar kaybolurdu); kullanıcıya elle değiştirmesi söylenir. Fusion'ın yaptığı bu
tek alanlık değişiklik, dosya önceden güvenilirse güveni bozmaz (komutlar değişmedi).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ..config import trust
from ..tools import launch_json, preview_launch

RPC_AUTO_VERIFY = "onizleme.otomatik_dogrulama"
_COMMENTED = "{dosya} yorum içeriyor; autoVerify değerini dosyada elle değiştir."


def _target(root: Path) -> Path:
    for relative in preview_launch.LAUNCH_FILES:
        if (root / relative).is_file():
            return root / relative
    return root / preview_launch.LAUNCH_FILE


def set_auto_verify(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("deger")
    if not isinstance(value, bool):
        return {"ok": False, "metin": "autoVerify için true ya da false gerekir."}
    path = _target(root)
    relative = path.relative_to(root).as_posix()
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError as error:
        return {"ok": False, "metin": f"{relative} okunamadı: {error}"}
    if text and launch_json.strip_json_comments(text) != text:
        return {"ok": False, "metin": _COMMENTED.format(dosya=relative)}
    try:
        raw = json.loads(text) if text.strip() else {"version": "0.0.1", "configurations": []}
    except ValueError as error:
        return {"ok": False, "metin": f"{relative} geçerli JSON değil: {error}"}
    if not isinstance(raw, dict):
        return {"ok": False, "metin": f"{relative}: üst düzeyde nesne bekleniyor."}
    was_trusted = bool(text) and trust.is_file_trusted(root, path)
    _write(path, {**raw, "autoVerify": value})
    if was_trusted:
        trust.approve_file(root, path)
    return {"ok": True, "otomatik_dogrulama": value, "dosya": relative}


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".launch-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
