"""Faz 3 — görev sınıflandırıcı + doğrulamayı derse bağlama.

Sınıflandırıcı saf eşleme olarak; doğrulama kararı saf; CommandVerifier gerçek ama
hafif kabuk komutlarıyla (true/false) test edilir — ağ/model yok.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent.classify import (
    TaskKind,
    classify_task,
    recall_scope,
    scope_of,
)
from fusion_cli.engines.agent.verification import CommandVerifier, resolve_turn_success

from .fakes import make_config

# --------------------------------------------------------------------------- #
# Sınıflandırıcı — saf
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("request_text", "expected"),
    [
        ("Login sayfasındaki hatayı düzelt", TaskKind.BUGFIX),
        ("Bu fonksiyon için pytest testi yaz", TaskKind.TEST),
        ("Şu modülü refactor et ve böl", TaskKind.REFACTOR),
        ("Bir landing sayfası için HTML oluştur", TaskKind.WEBSITE),
        ("README dosyasına kurulum belgesi ekle", TaskKind.DOCS),
        ("Yeni bir özellik ekle: dışa aktarma", TaskKind.FEATURE),
        ("Auth nerede yönetiliyor, incele", TaskKind.EXPLORE),
        ("selam nasılsın", TaskKind.GENERAL),
    ],
)
def test_siniflandirici_dogru_turu_secer(request_text, expected):
    assert classify_task(request_text) is expected


def test_bugfix_test_ten_once_gelir_oncelik():
    # Hem "test" hem "hata" geçiyor; öncelik sırası bugfix'i seçmeli.
    assert classify_task("testteki hatayı düzelt") is TaskKind.BUGFIX


def test_scope_of_general_bos_doner():
    assert scope_of(TaskKind.GENERAL) == ""
    assert scope_of(TaskKind.BUGFIX) == "bugfix"


def test_recall_scope_general_filtre_uygulamaz():
    assert recall_scope(TaskKind.GENERAL) is None
    assert recall_scope(TaskKind.REFACTOR) == "refactor"


# --------------------------------------------------------------------------- #
# Doğrulama kararı — saf
# --------------------------------------------------------------------------- #


def test_dogrulama_yokken_temel_sinyal_kullanilir():
    assert resolve_turn_success(outcome_ok=True, hit_step_limit=False, verification=None) is True
    assert resolve_turn_success(outcome_ok=False, hit_step_limit=False, verification=None) is False
    assert resolve_turn_success(outcome_ok=True, hit_step_limit=True, verification=None) is False


def test_dogrulama_gecerse_basarili():
    ok = VerificationResult(ok=True)
    assert resolve_turn_success(outcome_ok=True, hit_step_limit=False, verification=ok) is True


def test_dogrulama_kirikken_tur_basarisiz():
    fail = VerificationResult(ok=False, summary="pytest kırıldı")
    assert resolve_turn_success(outcome_ok=True, hit_step_limit=False, verification=fail) is False


def test_temel_sinyal_kotuyken_dogrulama_gecse_bile_basarisiz():
    ok = VerificationResult(ok=True)
    assert resolve_turn_success(outcome_ok=False, hit_step_limit=False, verification=ok) is False


# --------------------------------------------------------------------------- #
# CommandVerifier — gerçek ama hafif kabuk
# --------------------------------------------------------------------------- #


async def test_verifier_tum_komutlar_gecerse_ok(tmp_path):
    verifier = CommandVerifier(("true", "true"), cwd=str(tmp_path), timeout_s=10.0)
    result = await verifier.verify()
    assert result.ok is True


async def test_verifier_ilk_basarisiz_komutta_durur(tmp_path):
    verifier = CommandVerifier(("false", "true"), cwd=str(tmp_path), timeout_s=10.0)
    result = await verifier.verify()
    assert result.ok is False
    assert "false" in result.summary


async def test_verifier_zaman_asimi_basarisizlik(tmp_path):
    verifier = CommandVerifier(("sleep 5",), cwd=str(tmp_path), timeout_s=0.2)
    result = await verifier.verify()
    assert result.ok is False
    assert "zaman aşımı" in result.summary


async def test_verifier_basarisiz_komutta_bulgu_uretir(tmp_path):
    """Özet tek başına yetmez: motor düzeltici turu `findings` doluysa açar.

    Bulgu üretilmezse `pytest` kırmızıyken bile agent düzeltmeye hiç başlamaz;
    kapı yalnızca ders güvenini etkiler ve sessizce işlevsiz kalır.
    """
    verifier = CommandVerifier(("false",), cwd=str(tmp_path), timeout_s=10.0)

    result = await verifier.verify()

    assert result.ok is False
    assert result.findings, "başarısız komut bulgu üretmeli"


async def test_verifier_bulgusu_hata_ciktisini_tasir(tmp_path):
    """Modele "bir sorun var" değil, sorunun METNİ gitmeli."""
    komut = "echo 'AssertionError: beklenen 3 alinan 4' >&2; exit 1"
    verifier = CommandVerifier((komut,), cwd=str(tmp_path), timeout_s=10.0)

    result = await verifier.verify()

    assert result.ok is False
    birlesik = "\n".join(result.findings)
    assert "AssertionError: beklenen 3 alinan 4" in birlesik


async def test_verifier_uzun_ciktiyi_kirpar(tmp_path):
    """Binlerce satırlık test çıktısı prompt'a olduğu gibi girmemeli."""
    komut = "for i in $(seq 1 2000); do echo satir-$i; done; exit 1"
    verifier = CommandVerifier((komut,), cwd=str(tmp_path), timeout_s=30.0)

    result = await verifier.verify()

    birlesik = "\n".join(result.findings)
    assert result.ok is False
    assert "satir-2000" in birlesik, "kuyruk tutulmalı: hata en sonda olur"
    assert "satir-1" not in birlesik.split("\n")[0], "baş taraf kırpılmalı"
    assert len(birlesik) < 20_000


async def test_verifier_bos_komut_listesi_ok(tmp_path):
    verifier = CommandVerifier((), cwd=str(tmp_path), timeout_s=10.0)
    assert (await verifier.verify()).ok is True


# --- Web doğrulayıcının kurulumu --------------------------------------------- #


async def test_web_dogrulayici_varsayilan_olarak_kurulur(tmp_path):
    """Komut yapılandırılmamış olsa bile web kapısı çalışır."""
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.verification import build_verifier

    context = ToolContext(root=tmp_path)

    assert build_verifier(make_config(), root=tmp_path, tool_context=context) is not None


async def test_tum_kapilar_kapatilabilir(tmp_path):
    """Hiçbir kapı etkin değilse doğrulama tamamen kapalıdır."""
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.verification import build_verifier

    config = make_config(runtime={"web_verification": False, "browser_verification": False})

    assert build_verifier(config, root=tmp_path, tool_context=ToolContext(root=tmp_path)) is None


async def test_kapilar_ayri_ayri_kapatilabilir(tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.verification import BrowserVerifier, WebVerifier, build_verifier

    context = ToolContext(root=tmp_path)

    yalniz_tarayici = build_verifier(
        make_config(runtime={"web_verification": False}), root=tmp_path, tool_context=context
    )
    yalniz_metin = build_verifier(
        make_config(runtime={"browser_verification": False}), root=tmp_path, tool_context=context
    )

    assert isinstance(yalniz_tarayici, BrowserVerifier)
    assert isinstance(yalniz_metin, WebVerifier)


async def test_web_dogrulayici_yalnizca_dokunulan_dosyalara_bakar(tmp_path):
    """Agent'ın hiç görmediği dosya bulgu üretmemeli."""
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.verification import WebVerifier

    (tmp_path / "yabanci.html").write_text('<a href="#">x</a>', encoding="utf-8")
    yazilan = tmp_path / "benim.html"
    yazilan.write_text("<main>temiz</main>", encoding="utf-8")
    context = ToolContext(root=tmp_path)
    context.touched.add(yazilan)

    sonuc = await WebVerifier(context).verify()

    assert sonuc.ok, sonuc.findings


async def test_web_dogrulayici_bulgulari_tasir(tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.verification import WebVerifier

    yazilan = tmp_path / "a.html"
    yazilan.write_text('<img src="https://via.placeholder.com/80">', encoding="utf-8")
    context = ToolContext(root=tmp_path)
    context.touched.add(yazilan)

    sonuc = await WebVerifier(context).verify()

    assert not sonuc.ok
    assert any("placeholder" in bulgu for bulgu in sonuc.findings)


async def test_silinen_dosya_kapiyi_dusurmez(tmp_path):
    """Agent yazıp sonra sildiyse doğrulama çökmemeli."""
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.verification import WebVerifier

    context = ToolContext(root=tmp_path)
    context.touched.add(tmp_path / "yok.html")

    assert (await WebVerifier(context).verify()).ok


# --- Sınıflandırma gücü ------------------------------------------------------ #


def test_tesadufi_tek_kelime_dort_isabetli_kelimeyi_yenmez():
    """Gerçek hata: bir e-ticaret sayfası isteği REFACTOR sanılıyordu.

    Kampanya metnindeki "Kahve keyfini evine taşı" cümlesi REFACTOR'ın tek anahtar
    kelimesiyle eşleşiyor, WEBSITE ise dört kelimeyle (sayfa, html, css, arayüz)
    eşleşiyordu. "İlk eşleşen kazanır" kuralı tesadüfi eşleşmeyi öne alıyordu.
    """
    istek = (
        "Modern bir e-ticaret ana sayfası oluştur: index.html, style.css ve script.js. "
        "Kampanya bannerı: 'Kahve keyfini evine taşı'. Tüm arayüz Türkçe olsun."
    )

    assert classify_task(istek) is TaskKind.WEBSITE


def test_esit_guclu_eslesmede_oncelik_sirasi_korunur():
    """Beraberlikte kural sırası (özgülden genele) hâlâ belirleyici."""
    # Her iki tür de TEK kelimeyle eşleşiyor: bugfix "düzelt", feature "ekle".
    istek = "bunu düzelt ve şunu ekle"

    assert classify_task(istek) is TaskKind.BUGFIX
