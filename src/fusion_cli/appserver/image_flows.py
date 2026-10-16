"""Görsel iş akışlarının ve galerinin kalıcı deposu (`gorsel.akis.*`, `gorsel.galeri`).

Akışlar kullanıcı veri dizininde JSON olarak durur; arayüz bunları yeniden
açıp çalıştırabilir. Galeri, üretilen görsellerin uygulama içi deposudur:
dosyalar Finder'da görünen bir klasöre kendiliğinden inmez, yalnız
`gorsel.kaydet` ile kullanıcının seçtiği yere kopyalanır.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from ..config.paths import user_data_dir
from ..core.atomic_file import AtomicCommitUncertainError, atomic_replace_text
from ..core.file_lease import FileLease
from ..memory.asset_catalog import AssetCatalog
from .asset_paths import catalog_fields, scoped_files

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
_MAX_NODE_ID = 80
_FLOW_SCHEMA = 1
#: Arayüz GIRDI_KURALI ile aynı kabul edilen portlar; eksik port taslakta kalabilir.
_INPUT_KINDS = {
    "metin": frozenset(),
    "gorsel": frozenset(),
    "uret": frozenset({"metin", "gorsel"}),
    "varyasyon": frozenset({"metin", "gorsel"}),
    "buyut": frozenset({"gorsel"}),
    "duzenle": frozenset({"metin", "gorsel"}),
    "cikti": frozenset({"gorsel"}),
}


def gallery_dir() -> Path:
    return user_data_dir() / "gallery"


def flows_dir() -> Path:
    return user_data_dir() / "image-flows"


class FlowError(ValueError):
    """Akış verisi sözleşmeye uymuyor; mesaj kullanıcıya gösterilir."""


def _text(value: object, limit: int = _MAX_TEXT) -> str:
    return value[:limit] if isinstance(value, str) else ""


def _number(value: object) -> float:
    if value is None:
        return 0.0
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise FlowError("Düğüm konumu sayı olmalı.")
    try:
        result = float(value)
    except OverflowError as error:
        raise FlowError("Düğüm konumu sonlu olmalı.") from error
    if not math.isfinite(result):
        raise FlowError("Düğüm konumu sonlu olmalı.")
    return result


def _validate_graph(ids: set[str], edges: list[dict[str, str]]) -> None:
    """Bağlantısız bileşenler dahil tüm akışın yönlü çevrimsiz olduğunu doğrula."""
    successors: dict[str, list[str]] = {node_id: [] for node_id in ids}
    incoming = dict.fromkeys(ids, 0)
    seen: set[tuple[str, str]] = set()
    for edge in edges:
        source, target = edge["kaynak"], edge["hedef"]
        if source == target or (source, target) in seen:
            raise FlowError("Bağlantı yinelenemez veya kendi düğümüne dönemez.")
        seen.add((source, target))
        successors[source].append(target)
        incoming[target] += 1
    ready = [node_id for node_id, count in incoming.items() if count == 0]
    visited = 0
    while ready:
        node_id = ready.pop()
        visited += 1
        for target in successors[node_id]:
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
    if visited != len(ids):
        raise FlowError("Akış döngü içeriyor.")


def _validate_ports(nodes: list[dict[str, Any]], edges: list[dict[str, str]]) -> None:
    types = {node["id"]: node["tur"] for node in nodes}
    occupied: set[tuple[str, str]] = set()
    for edge in edges:
        source_type = types[edge["kaynak"]]
        kind = "metin" if source_type == "metin" else "gorsel"
        port = (edge["hedef"], kind)
        if source_type == "cikti" or kind not in _INPUT_KINDS[types[edge["hedef"]]]:
            raise FlowError("Bağlantı hedefin kabul ettiği girdi türüne uymuyor.")
        if port in occupied:
            raise FlowError("Aynı girdi portuna birden çok bağlantı yapılamaz.")
        occupied.add(port)


def _clean_node(node: object) -> dict[str, Any]:
    if (
        not isinstance(node, dict)
        or not isinstance(node.get("tur"), str)
        or node["tur"] not in _NODE_TYPES
    ):
        raise FlowError("Bilinmeyen düğüm türü.")
    node_id = node.get("id")
    if not isinstance(node_id, str) or not node_id.strip() or len(node_id) > _MAX_NODE_ID:
        raise FlowError("Düğüm kimliği boş veya çok uzun.")
    clean: dict[str, Any] = {
        "id": node_id,
        "tur": node["tur"],
        "x": _number(node.get("x")),
        "y": _number(node.get("y")),
    }
    for key in ("istem", "yol", "saglayici", "oran"):
        if isinstance(node.get(key), str):
            clean[key] = _text(node[key])
    if "adet" in node:
        count = node["adet"]
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not 1 <= count <= _MAX_VARIATIONS
        ):
            raise FlowError("Varyasyon sayısı desteklenen aralıkta tam sayı olmalı.")
        clean["adet"] = count
    return clean


def validate_flow(raw: object) -> dict[str, Any]:
    """Akışı doğrulayıp yalnız bilinen alanlarla YENİ bir sözlük döndür."""
    if not isinstance(raw, dict):
        raise FlowError("Akış bir nesne olmalı.")
    if "schema_version" in raw and (
        isinstance(raw["schema_version"], bool) or raw["schema_version"] != _FLOW_SCHEMA
    ):
        raise FlowError("Akış sürümü desteklenmiyor.")
    nodes_raw = raw.get("dugumler")
    edges_raw = raw.get("baglantilar")
    if not isinstance(nodes_raw, list) or not isinstance(edges_raw, list):
        raise FlowError("Akışta düğüm ve bağlantı listeleri olmalı.")
    if len(nodes_raw) > _MAX_NODES or len(edges_raw) > _MAX_NODES * 2:
        raise FlowError("Akış çok büyük.")
    nodes = [_clean_node(node) for node in nodes_raw]
    ids = {node["id"] for node in nodes}
    if len(ids) != len(nodes):
        raise FlowError("Düğüm kimlikleri benzersiz olmalı.")
    edges = []
    for edge in edges_raw:
        if (
            not isinstance(edge, dict)
            or not isinstance(edge.get("kaynak"), str)
            or not isinstance(edge.get("hedef"), str)
            or edge.get("kaynak") not in ids
            or edge.get("hedef") not in ids
        ):
            raise FlowError("Bağlantı var olmayan düğüme gidiyor.")
        edges.append({"kaynak": edge["kaynak"], "hedef": edge["hedef"]})
    _validate_graph(ids, edges)
    _validate_ports(nodes, edges)
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
    expected = data["akis"].get("revision", 0)
    lease = FileLease(base / f"{flow_id}.lock")
    try:
        if not lease.try_acquire():
            raise FlowError("Akış başka bir yazıcı tarafından kaydediliyor.")
        target = base / f"{flow_id}.json"
        revision = (
            _flow_revision(json.loads(target.read_text(encoding="utf-8"))) if target.exists() else 0
        )
        if isinstance(expected, bool) or not isinstance(expected, int) or expected != revision:
            raise FlowError("Akış başka bir yerde değişti; güncel kaydı yeniden aç.")
        revision += 1
        atomic_replace_text(
            target,
            json.dumps(
                {**flow, "id": flow_id, "schema_version": _FLOW_SCHEMA, "revision": revision},
                ensure_ascii=False,
            ),
        )
        return {"ok": True, "id": flow_id, "revision": revision}
    except AtomicCommitUncertainError:
        return {
            "ok": False,
            "committed": True,
            "id": flow_id,
            "revision": revision,
            "metin": "Akış yazıldı; kalıcılığı doğrulanamadı. Yeniden açarak kontrol et.",
        }
    except (OSError, UnicodeError, ValueError) as error:
        return {
            "ok": False,
            "metin": str(error) if isinstance(error, FlowError) else "Akış kaydedilemedi.",
        }
    finally:
        lease.close()


def _flow_revision(raw: object) -> int:
    """Legacy sürümsüz kayıt revision0 olarak yalnız bir kez göç edebilir."""
    validate_flow(raw)
    assert isinstance(raw, dict)
    revision: object = raw.get("revision", 0)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise FlowError("Akış kayıt sürümü geçersiz.")
    if "schema_version" in raw and revision == 0:
        raise FlowError("Akış kayıt sürümü eksik.")
    return revision


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
        raw = json.loads(path.read_text(encoding="utf-8"))
        revision = _flow_revision(raw)
        flow = validate_flow(raw)
    except (OSError, ValueError) as error:
        return {"ok": False, "metin": f"Akış açılamadı: {error}"}
    return {"ok": True, "akis": {**flow, "id": flow_id, "revision": revision}}


def write_sidecar(image: Path, *, prompt: str, provider: str) -> None:
    """Galeri künyesini atomik yayımla; mevcut sembolik bağı izleyerek yazma."""
    meta = {"istem": prompt[:_MAX_TEXT], "saglayici": provider[:_MAX_NAME]}
    atomic_replace_text(
        image.with_suffix(image.suffix + ".json"), json.dumps(meta, ensure_ascii=False)
    )


def list_gallery(
    directory: Path | None = None, *, catalog: AssetCatalog | None = None
) -> dict[str, Any]:
    base = directory or gallery_dir()
    if not base.is_dir():
        return {"ok": True, "dosyalar": []}
    images = sorted(
        scoped_files(base, frozenset(_IMAGE_SUFFIXES)), key=lambda item: item[1], reverse=True
    )
    files = []
    for image, _stamp in images:
        meta: dict[str, Any] = {}
        sidecar = image.with_suffix(image.suffix + ".json")
        if sidecar.is_file() and not sidecar.is_symlink():
            try:
                raw_meta: object = json.loads(sidecar.read_text(encoding="utf-8"))
                meta = raw_meta if isinstance(raw_meta, dict) else {}
            except (OSError, ValueError):
                meta = {}
        files.append(
            {
                **catalog_fields(catalog, "gallery", image, base),
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
