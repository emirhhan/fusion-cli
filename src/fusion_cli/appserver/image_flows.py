"""Görsel iş akışlarının ve galerinin kalıcı deposu (`gorsel.akis.*`, `gorsel.galeri`).

Akışlar kullanıcı veri dizininde JSON olarak durur; arayüz bunları yeniden
açıp çalıştırabilir. Galeri, üretilen görsellerin uygulama içi deposudur:
dosyalar Finder'da görünen bir klasöre kendiliğinden inmez, yalnız
`gorsel.kaydet` ile kullanıcının seçtiği yere kopyalanır.
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from ..config.paths import user_data_dir

#: Düğüm türleri arayüzdeki `imagecreate/akis.ts::DugumTuru` ile aynıdır.
_NODE_TYPES = frozenset({"metin", "gorsel", "uret", "varyasyon", "buyut", "duzenle", "cikti"})
#: Kötü niyetli ya da bozuk dosyanın belleği şişirmemesi için üst sınırlar; bir
#: tuvalde elle kurulan akış için geniş, ama sınırsız değil.
_MAX_NODES = 200
_MAX_TEXT = 4_000
_MAX_NAME = 120
#: Düğüm başına varyasyon üst sınırı: `app/src/imagecreate/akis.ts::MAX_ADET`.
_MAX_VARIATIONS = 4
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")
_FLOW_ID = re.compile(r"^[0-9a-f]{32}$")


def gallery_dir() -> Path:
    return user_data_dir() / "gallery"


def flows_dir() -> Path:
    return user_data_dir() / "image-flows"


class FlowError(ValueError):
    """Akış verisi sözleşmeye uymuyor; mesaj kullanıcıya gösterilir."""


def _text(value: object, limit: int = _MAX_TEXT) -> str:
    return value[:limit] if isinstance(value, str) else ""


def _number(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def validate_flow(raw: object) -> dict[str, Any]:
    """Akışı doğrulayıp yalnız bilinen alanlarla YENİ bir sözlük döndür."""
    if not isinstance(raw, dict):
        raise FlowError("Akış bir nesne olmalı.")
    nodes_raw = raw.get("dugumler")
    edges_raw = raw.get("baglantilar")
    if not isinstance(nodes_raw, list) or not isinstance(edges_raw, list):
        raise FlowError("Akışta düğüm ve bağlantı listeleri olmalı.")
    if len(nodes_raw) > _MAX_NODES or len(edges_raw) > _MAX_NODES * 2:
        raise FlowError("Akış çok büyük.")
    nodes: list[dict[str, Any]] = []
    for node in nodes_raw:
        if not isinstance(node, dict) or node.get("tur") not in _NODE_TYPES:
            raise FlowError("Bilinmeyen düğüm türü.")
        node_id = _text(node.get("id"), 80)
        if not node_id:
            raise FlowError("Düğüm kimliği boş.")
        clean: dict[str, Any] = {
            "id": node_id,
            "tur": node["tur"],
            "x": _number(node.get("x")),
            "y": _number(node.get("y")),
        }
        for key in ("istem", "yol", "saglayici", "oran"):
            if isinstance(node.get(key), str):
                clean[key] = _text(node[key])
        adet = node.get("adet")
        # Arayüzdeki `MAX_ADET` ile aynı aralık; dışındaki değer saklanmaz.
        if isinstance(adet, int) and not isinstance(adet, bool) and 1 <= adet <= _MAX_VARIATIONS:
            clean["adet"] = adet
        nodes.append(clean)
    ids = {node["id"] for node in nodes}
    edges = []
    for edge in edges_raw:
        if (
            not isinstance(edge, dict)
            or edge.get("kaynak") not in ids
            or edge.get("hedef") not in ids
        ):
            raise FlowError("Bağlantı var olmayan düğüme gidiyor.")
        edges.append({"kaynak": edge["kaynak"], "hedef": edge["hedef"]})
    name = _text(raw.get("ad"), _MAX_NAME).strip() or "Adsız akış"
    return {"ad": name, "dugumler": nodes, "baglantilar": edges}


def save_flow(data: dict[str, Any], directory: Path | None = None) -> dict[str, Any]:
    base = directory or flows_dir()
    try:
        flow = validate_flow(data.get("akis"))
    except FlowError as error:
        return {"ok": False, "metin": str(error)}
    raw_id = data.get("akis", {}).get("id") if isinstance(data.get("akis"), dict) else None
    flow_id = raw_id if isinstance(raw_id, str) and _FLOW_ID.match(raw_id) else uuid.uuid4().hex
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{flow_id}.json").write_text(
        json.dumps({**flow, "id": flow_id}, ensure_ascii=False), encoding="utf-8"
    )
    return {"ok": True, "id": flow_id}


def list_flows(directory: Path | None = None) -> dict[str, Any]:
    base = directory or flows_dir()
    items = []
    paths = sorted(base.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in paths if base.is_dir() else ():
        try:
            name = json.loads(path.read_text(encoding="utf-8")).get("ad", "")
        except (OSError, ValueError):
            continue
        items.append({"id": path.stem, "ad": _text(name, _MAX_NAME) or "Adsız akış"})
    return {"ok": True, "akislar": items}


def load_flow(data: dict[str, Any], directory: Path | None = None) -> dict[str, Any]:
    flow_id = data.get("id")
    if not isinstance(flow_id, str) or not _FLOW_ID.match(flow_id):
        return {"ok": False, "metin": "Geçersiz akış kimliği."}
    path = (directory or flows_dir()) / f"{flow_id}.json"
    try:
        flow = validate_flow(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        return {"ok": False, "metin": f"Akış açılamadı: {error}"}
    return {"ok": True, "akis": {**flow, "id": flow_id}}


def write_sidecar(image: Path, *, prompt: str, provider: str) -> None:
    """Galerideki görselin istemini ve sağlayıcısını yanına yaz (galeri listesi için)."""
    meta = {"istem": prompt[:_MAX_TEXT], "saglayici": provider[:_MAX_NAME]}
    image.with_suffix(image.suffix + ".json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )


def list_gallery(directory: Path | None = None) -> dict[str, Any]:
    base = directory or gallery_dir()
    if not base.is_dir():
        return {"ok": True, "dosyalar": []}
    images = [p for p in base.iterdir() if p.suffix.lower() in _IMAGE_SUFFIXES]
    images.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    files = []
    for image in images:
        meta: dict[str, Any] = {}
        sidecar = image.with_suffix(image.suffix + ".json")
        if sidecar.is_file():
            try:
                meta = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
        files.append(
            {
                "yol": str(image),
                "istem": _text(meta.get("istem")),
                "saglayici": _text(meta.get("saglayici"), _MAX_NAME),
            }
        )
    return {"ok": True, "dosyalar": files}


def export_image(data: dict[str, Any], directory: Path | None = None) -> dict[str, Any]:
    """Galerideki görseli kullanıcının seçtiği yere kopyala ("İndir")."""
    base = (directory or gallery_dir()).resolve()
    source_raw, target_raw = data.get("yol"), data.get("hedef")
    if not isinstance(source_raw, str) or not isinstance(target_raw, str):
        return {"ok": False, "metin": "Kaynak ve hedef yolu gerekli."}
    source = Path(source_raw).resolve()
    if not source.is_relative_to(base) or not source.is_file():
        return {"ok": False, "metin": "Yalnız galerideki görseller kaydedilebilir."}
    target = Path(target_raw).expanduser()
    if not target.is_absolute() or target.suffix.lower() not in _IMAGE_SUFFIXES:
        return {"ok": False, "metin": "Hedef .png ya da .jpg uzantılı tam bir yol olmalı."}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    except OSError as error:
        return {"ok": False, "metin": f"Kaydedilemedi: {error}"}
    return {"ok": True, "yol": str(target)}
