"""Ders kataloğu protokolünün sözleşmesi: sekiz ders, güvenli eylem, hatasız kimlik."""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.appserver.lessons import BUILTIN_LESSONS, get_lesson, list_lessons
from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession

_KNOWN_ACTION_KEYS = {
    "composer": {"tur", "gorev"},
    "sekme": {"tur", "hedef"},
}
_FORBIDDEN_ACTION_TOKENS = ("komut", "command", "shell", "exec", "run", "cmd", "argv")


async def _request(session: AppSession, lines: list[str], name: str, data: dict[str, object]):
    await session.handle(Request(id=name, name=name, data=data))
    return json.loads(lines[-1])["veri"]


def _assert_action_is_safe(eylem: dict[str, object]) -> None:
    """Hiçbir eylem yürütülebilir komut, dosya yolu ya da ağ adresi taşımaz."""
    kind = eylem.get("tur")
    assert kind in _KNOWN_ACTION_KEYS
    assert set(eylem) == _KNOWN_ACTION_KEYS[kind]
    for forbidden in _FORBIDDEN_ACTION_TOKENS:
        assert forbidden not in eylem


def test_yerlesik_ders_katalogunda_sekiz_ders_var():
    assert len(BUILTIN_LESSONS) == 8
    assert len({lesson.id for lesson in BUILTIN_LESSONS}) == 8


def test_hicbir_ders_adiminin_eylemi_yurutulebilir_komut_tasimaz():
    for lesson in BUILTIN_LESSONS:
        assert lesson.adimlar, f"{lesson.id} adımsız olamaz"
        for step in lesson.adimlar:
            _assert_action_is_safe(step.eylem.to_payload())


def test_ders_listele_dogrudan_cagrildiginda_sekiz_ozet_dondurur():
    result = list_lessons()

    assert result["ok"] is True
    assert len(result["dersler"]) == 8
    for entry in result["dersler"]:
        assert entry.keys() == {"id", "baslik", "ozet", "adim_sayisi"}
        assert entry["adim_sayisi"] > 0


def test_ders_getir_dogrudan_cagrildiginda_bilinmeyen_kimlik_cokmeden_hata_dondurur():
    result = get_lesson("olmayan-ders-kimligi")

    assert result == {"ok": False, "metin": "Ders bulunamadı: olmayan-ders-kimligi"}


async def test_ders_listele_protokol_uzerinden_sekiz_dersi_dondurur(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=tmp_path / "home")

    result = await _request(session, lines, "ders.listele", {})
    await session.close()

    assert result["ok"] is True
    assert len(result["dersler"]) == 8
    assert result["dersler"][0]["id"] == "ilk-proje"


async def test_ders_getir_protokol_uzerinden_adimlari_ve_guvenli_eylemi_dondurur(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=tmp_path / "home")

    result = await _request(session, lines, "ders.getir", {"id": "ilk-proje"})
    await session.close()

    assert result["ok"] is True
    assert result["id"] == "ilk-proje"
    assert len(result["adimlar"]) > 0
    for step in result["adimlar"]:
        assert step.keys() == {"id", "baslik", "aciklama", "onizleme", "eylem"}
        _assert_action_is_safe(step["eylem"])


async def test_ders_getir_protokol_uzerinden_bilinmeyen_kimlikte_sureci_cokertmez(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=tmp_path / "home")

    result = await _request(session, lines, "ders.getir", {"id": "yok-boyle-bir-ders"})
    await session.close()

    assert result == {"ok": False, "metin": "Ders bulunamadı: yok-boyle-bir-ders"}


def test_her_ders_alti_yedi_adim_tasir():
    """Ders "bahsetme" değil, gerçekten öğreten bir akış olmalı.

    Kullanıcı denedi ve "sadece bahsetmeler var, 6-7 sayfadan oluşsun" dedi.
    Adım sayısı bu yüzden sözleşmenin parçasıdır: içerik sığlaşırsa test düşer.
    """
    for lesson in BUILTIN_LESSONS:
        assert 6 <= len(lesson.adimlar) <= 7, f"{lesson.id}: {len(lesson.adimlar)} adım"


def test_her_adim_onizleme_tasir():
    """Kullanıcı denemeden ÖNCE ne olacağını görmeli.

    Composer eyleminde önizleme gönderilecek metnin tam hali, sekme eyleminde
    o sekmede ne göreceğinin kısa tarifidir.
    """
    for lesson in BUILTIN_LESSONS:
        for step in lesson.adimlar:
            payload = step.to_payload()
            assert payload["onizleme"].strip(), f"{lesson.id}/{step.id} önizlemesiz"
            assert len(payload["aciklama"]) > 40, f"{lesson.id}/{step.id} açıklaması sığ"
