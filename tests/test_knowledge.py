"""Faz 7 — ortak bilgi paketi: imza/bütünlük doğrulama, sync farkı, uygulama.

İmza kontrolü, manifest bütünlüğü, sır taraması ve "yalnızca değişeni indir" mantığı
saf test edilir. Servis katmanı sahte bir ders belleğiyle (ağsız) sınanır.
"""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.core.memory import Lesson
from fusion_cli.knowledge import (
    KnowledgeEntry,
    build_manifest,
    plan_sync,
    validate_manifest,
)
from fusion_cli.knowledge.manifest import with_hashes
from fusion_cli.knowledge.package import (
    manifest_from_dict,
    manifest_to_dict,
    read_manifest,
    write_manifest,
)
from fusion_cli.knowledge.service import load_state, sync
from fusion_cli.knowledge.signing import generate_keypair

#: Test için tek bir Ed25519 çifti: PRIVATE ile imzalanır, PUBLIC ile doğrulanır.
_PRIVATE_KEY, _PUBLIC_KEY = generate_keypair()


def _entries() -> tuple[KnowledgeEntry, ...]:
    return (
        KnowledgeEntry(entry_id="e1", text="dosyayi once oku", kind="success", scope="bugfix"),
        KnowledgeEntry(entry_id="e2", text="testi silme", kind="mistake"),
    )


# --------------------------------------------------------------------------- #
# Ed25519 imza (asimetrik)
# --------------------------------------------------------------------------- #


def test_ed25519_ozel_anahtarla_imza_acik_anahtarla_dogrulanir():
    from fusion_cli.knowledge.signing import sign, verify

    yuk = b"dogrulanacak icerik"
    imza = sign(yuk, _PRIVATE_KEY)
    assert verify(yuk, imza, _PUBLIC_KEY) is True


def test_ed25519_oynanmis_yuk_dogrulanmaz():
    from fusion_cli.knowledge.signing import sign, verify

    imza = sign(b"orijinal", _PRIVATE_KEY)
    assert verify(b"degistirilmis", imza, _PUBLIC_KEY) is False


def test_ed25519_bozuk_imza_istisna_firlatmaz():
    from fusion_cli.knowledge.signing import verify

    # Bozuk hex/imza baytları False dönmeli, çökme değil.
    assert verify(b"x", "zzz-gecersiz-hex", _PUBLIC_KEY) is False


# --------------------------------------------------------------------------- #
# İmza + bütünlük doğrulama
# --------------------------------------------------------------------------- #


def test_imzali_paket_dogrulanir():
    manifest = build_manifest(_entries(), version=1, private_key=_PRIVATE_KEY)
    result = validate_manifest(manifest, public_key=_PUBLIC_KEY)
    assert result.ok is True


def test_baska_acik_anahtar_imzayi_reddeder():
    # Farklı bir çiftin AÇIK anahtarıyla doğrulama: imza tutmamalı.
    _, baska_public = generate_keypair()
    manifest = build_manifest(_entries(), version=1, private_key=_PRIVATE_KEY)
    result = validate_manifest(manifest, public_key=baska_public)
    assert result.ok is False
    assert any("imza" in problem for problem in result.problems)


def test_icerik_oynanirsa_butunluk_kirilir():
    manifest = build_manifest(_entries(), version=1, private_key=_PRIVATE_KEY)
    # Bir girişin metnini imza sonrası değiştir (hash artık uyuşmaz).
    tampered_entries = (replace(manifest.entries[0], text="ELE GECIRILDI"), manifest.entries[1])
    tampered = replace(manifest, entries=tampered_entries)
    result = validate_manifest(tampered, public_key=_PUBLIC_KEY)
    assert result.ok is False
    assert any("bütünlük" in problem for problem in result.problems)


def test_sir_iceren_giris_reddedilir():
    secret_entry = KnowledgeEntry(
        entry_id="s1", text="anahtar sk-ABCDEFGH1234567890abcd", kind="success"
    )
    manifest = build_manifest((secret_entry,), version=1, private_key=_PRIVATE_KEY)
    result = validate_manifest(manifest, public_key=_PUBLIC_KEY)
    assert result.ok is False
    assert any("sır" in problem for problem in result.problems)


# --------------------------------------------------------------------------- #
# Sync farkı (yalnızca değişeni indir)
# --------------------------------------------------------------------------- #


def test_sync_yeni_ve_degiseni_ayirir():
    manifest = build_manifest(_entries(), version=1, private_key=_PRIVATE_KEY)
    e1_hash = manifest.entries[0].content_hash
    # e1 bilinen ve GÜNCEL; e2 hiç bilinmiyor (yeni).
    local = {"e1": e1_hash}
    plan = plan_sync(local, manifest)
    assert [e.entry_id for e in plan.added] == ["e2"]
    assert plan.updated == ()
    assert plan.unchanged == ("e1",)


def test_sync_degisen_hash_guncellenen_sayilir():
    manifest = build_manifest(_entries(), version=1, private_key=_PRIVATE_KEY)
    local = {"e1": "eski-hash", "e2": manifest.entries[1].content_hash}
    plan = plan_sync(local, manifest)
    assert [e.entry_id for e in plan.updated] == ["e1"]
    assert plan.added == ()


def test_sync_hepsi_guncelse_degisiklik_yok():
    manifest = build_manifest(_entries(), version=1, private_key=_PRIVATE_KEY)
    local = {e.entry_id: e.content_hash for e in manifest.entries}
    plan = plan_sync(local, manifest)
    assert plan.has_changes is False


# --------------------------------------------------------------------------- #
# Paket serileştirme
# --------------------------------------------------------------------------- #


def test_manifest_json_tur_turu_korunur():
    manifest = build_manifest(_entries(), version=2, private_key=_PRIVATE_KEY)
    restored = manifest_from_dict(manifest_to_dict(manifest))
    assert restored == manifest


def test_manifest_diske_yazilip_okununca_dogrulanir(tmp_path):
    manifest = build_manifest(_entries(), version=1, private_key=_PRIVATE_KEY)
    path = tmp_path / "manifest.json"
    write_manifest(manifest, path)
    restored = read_manifest(path)
    assert validate_manifest(restored, public_key=_PUBLIC_KEY).ok is True


def test_hash_alani_secilen_alanlardan_turetilir():
    entry = KnowledgeEntry(entry_id="e", text="metin", kind="success", scope="bugfix")
    hashed = with_hashes((entry,))[0]
    assert hashed.content_hash
    # Metin değişince hash de değişir.
    other = with_hashes((replace(entry, text="baska"),))[0]
    assert hashed.content_hash != other.content_hash


# --------------------------------------------------------------------------- #
# Servis: doğrula + yalnızca değişeni uygula + durum yaz
# --------------------------------------------------------------------------- #


class _FakeLessonMemory:
    def __init__(self) -> None:
        self.added: list[Lesson] = []

    def add(self, lesson: Lesson) -> bool:
        self.added.append(lesson)
        return True

    def recall(self, task: str, limit: int = 4, *, scope=None) -> tuple[Lesson, ...]:
        return ()

    def reinforce(self, texts: tuple[str, ...], *, success: bool) -> int:
        return 0

    def all(self) -> tuple[Lesson, ...]:
        return tuple(self.added)

    def count(self) -> int:
        return len(self.added)


def test_servis_gecerli_paketi_uygular_ve_durum_yazar(tmp_path):
    manifest = build_manifest(_entries(), version=1, private_key=_PRIVATE_KEY)
    memory = _FakeLessonMemory()
    state_path = tmp_path / "state.json"

    report = sync(manifest, memory, state_path=state_path, public_key=_PUBLIC_KEY)
    assert report.ok is True
    assert report.added == 2
    assert len(memory.added) == 2
    # Durum tüm girişlerin hash'iyle güncellenir → ikinci sync değişiklik uygulamaz.
    state = load_state(state_path)
    assert set(state) == {"e1", "e2"}

    again = sync(manifest, _FakeLessonMemory(), state_path=state_path, public_key=_PUBLIC_KEY)
    assert again.added == 0
    assert again.updated == 0


def test_servis_gecersiz_paketi_uygulamaz(tmp_path):
    manifest = build_manifest(_entries(), version=1, private_key=_PRIVATE_KEY)
    memory = _FakeLessonMemory()
    _, baska_public = generate_keypair()
    report = sync(manifest, memory, state_path=tmp_path / "state.json", public_key=baska_public)
    assert report.ok is False
    assert memory.added == []  # hiçbir ders uygulanmadı
