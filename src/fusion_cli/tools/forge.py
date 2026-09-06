"""Koşu içinde araç üretimi — ajan kendine görev-özel araç yazar.

Live-SWE-agent'ın ölçümü: yalnız bash ile başlayıp koşu sırasında kendine Python
araçları yazan ajan SWE-bench Verified'da %77,4 aldı, çevrimdışı eğitim maliyeti
sıfır. Kazancın kaynağı basit: tekrar eden mekanik işi (aynı dizini süzmek, aynı
biçimi ayrıştırmak, aynı raporu çıkarmak) bir kez yazıp sonraki adımlarda ÇAĞIRMAK.

Güvenlik gevşetilmez:

- Kaynak diske yazılmadan ÖNCE `compile` ile denetlenir; bozuk kod kaydedilmez.
- Araç `.fusion/tools/<ad>.py` altında durur ve adı yol kaçışı içeremez.
- Üretilen araç `ToolContext` alır: kök dışına yazma, `restrict_to_root` kuralıyla
  kapalıdır. Araç kodunu ajan yazdı diye erişim genişlemez.
- Aile `EXTERNAL`'dır: adım kapsamı ve onay kuralları aynen geçerlidir.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..core.tools import Tool, ToolArgs, ToolContext, ToolResult
from .args import require_str
from .files import resolve_path

#: Üretilen araçların yaşadığı dizin (proje kökü altında).
FORGE_DIR = ".fusion/tools"
_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def forge_tool(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Yeni bir araç yaz ve kaydet."""
    name = require_str(args, "name")
    source = require_str(args, "source")
    if not _SAFE_NAME.match(name):
        return ToolResult.failure(
            f"Geçersiz araç adı: {name}. Yalnız küçük harf, rakam ve alt çizgi kullan."
        )
    hata = _validate(source)
    if hata is not None:
        return ToolResult.failure(hata)
    hedef = context.root / FORGE_DIR / f"{name}.py"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(source, encoding="utf-8")
    context.changes.record(hedef)
    return ToolResult(f"araç üretildi: {name} ({hedef}). Sonraki adımlarda çağırabilirsin.")


def load_forged_tools(root: Path) -> tuple[Tool, ...]:
    """Üretilmiş araçları kayıt defterine hazır hâlde döndür."""
    dizin = root / FORGE_DIR
    if not dizin.is_dir():
        return ()
    return tuple(
        _build(path)
        for path in sorted(dizin.glob("*.py"))
        if _SAFE_NAME.match(path.stem) and _validate(_read(path)) is None
    )


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _validate(source: str) -> str | None:
    """Kaynak çalıştırılabilir ve sözleşmeye uygun mu?"""
    try:
        compile(source, "<forge>", "exec")
    except SyntaxError as hata:
        return f"Araç kaynağı geçersiz: Python sözdizimi hatası (satır {hata.lineno}): {hata.msg}"
    if not re.search(r"^def run\(", source, re.MULTILINE):
        return "Araç kaynağı `def run(args)` fonksiyonu tanımlamalı."
    return None


def _build(path: Path) -> Tool:
    """Kaynağı yükleyip `Tool` sözleşmesine sar."""

    def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        namespace: dict[str, Any] = {}
        try:
            exec(compile(_read(path), str(path), "exec"), namespace)
            islev = namespace.get("run")
            if not callable(islev):
                return ToolResult.failure(f"{path.stem}: `run` bulunamadı.")
            # Yol argümanları kök kuralından geçirilir: aracı ajan yazdı diye erişim
            # genişlemez; kök dışı yol burada reddedilir.
            for anahtar in ("path", "yol"):
                if isinstance(args.get(anahtar), str):
                    resolve_path(context, str(args[anahtar]))
            return ToolResult(str(islev(dict(args))))
        except Exception as hata:  # araç sınırı: hata modele okunur biçimde döner
            return ToolResult.failure(f"{path.stem} çalışırken hata: {type(hata).__name__}: {hata}")

    return Tool(
        name=path.stem,
        description=f"Koşu içinde üretilmiş araç ({path.name}).",
        parameters={"type": "object", "properties": {}},
        run=_run,
        mutating=True,
    )
