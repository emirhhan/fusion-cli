"""`search_code`/`glob` meşru kaynak dosyalarını ve klasörleri görünmez kılmaz (T2-02).

Ölçüldü (29 Ekim): adında auth/token/secret/private/settings geçen HER dosya (auth.py,
token.ts, use-auth.ts, settings.py) atlanıyor, glob da aynı süzgeci kullandığı için
`glob("**/auth*.ts")` boş dönüyordu; proje yolu `claude`, `cache`, `.config` gibi bir
klasör altındaysa MUTLAK yolun bileşenleri yüzünden HER dosya atlanıyordu. Atlama
sessizdi.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import build_registry

KAYNAKLAR = ("auth.py", "token.ts", "auth-service.ts", "use-auth.ts", "private.ts", "settings.py")


@pytest.fixture
def registry():
    return build_registry()


async def _calistir(registry, context, ad, **args):
    return await registry.execute(ad, args, context)


async def test_kaynak_dosyalar_arama_sonucunda_gorunur(registry, tmp_path):
    for ad in KAYNAKLAR:
        (tmp_path / ad).write_text("hedef_islev()\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    sonuc = await _calistir(registry, context, "search_code", pattern="hedef_islev")

    assert sonuc.ok
    assert all(ad in sonuc.output for ad in KAYNAKLAR), sonuc.output


async def test_glob_auth_dosyalarini_bulur(registry, tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth-service.ts").write_text("x", encoding="utf-8")
    (tmp_path / "src" / "use-auth.ts").write_text("x", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    sonuc = await _calistir(registry, context, "glob", pattern="**/*auth*.ts")

    assert sonuc.ok and "auth-service.ts" in sonuc.output and "use-auth.ts" in sonuc.output


async def test_glob_gizli_olabilecek_dosyanin_yalniz_adini_listeler(registry, tmp_path):
    (tmp_path / "config.json").write_text('{"token":"abcdefghijklmnop123456"}', encoding="utf-8")
    context = ToolContext(root=tmp_path)

    sonuc = await _calistir(registry, context, "glob", pattern="config.json")

    assert sonuc.ok and "config.json" in sonuc.output
    assert "abcdefghijklmnop123456" not in sonuc.output


@pytest.mark.parametrize(
    "ust_klasorler",
    [("claude",), (".config", "x"), ("Application Support",), ("cache", "vendor", "chrome")],
)
async def test_proje_yolu_ozel_adli_klasor_altinda_olsa_da_aranir(
    registry, tmp_path, ust_klasorler
):
    proje = tmp_path.joinpath(*ust_klasorler, "proje")
    proje.mkdir(parents=True)
    (proje / "app.py").write_text("hedef_islev()\n", encoding="utf-8")
    context = ToolContext(root=proje)

    arama = await _calistir(registry, context, "search_code", pattern="hedef_islev")
    liste = await _calistir(registry, context, "glob", pattern="*.py")

    assert arama.ok and "app.py" in arama.output
    assert liste.ok and "app.py" in liste.output


async def test_kok_altindaki_vendor_klasoru_hala_budanir(registry, tmp_path):
    (tmp_path / "vendor" / "paket").mkdir(parents=True)
    (tmp_path / "vendor" / "paket" / "lib.py").write_text("hedef_islev()\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    sonuc = await _calistir(registry, context, "search_code", pattern="hedef_islev")

    assert "lib.py" not in sonuc.output


async def test_kimlik_deposu_klasoru_kokun_atasi_olsa_da_korunur(registry, tmp_path):
    proje = tmp_path / ".ssh" / "proje"
    proje.mkdir(parents=True)
    (proje / "notlar.txt").write_text("hedef_islev\n", encoding="utf-8")
    context = ToolContext(root=proje)

    sonuc = await _calistir(registry, context, "search_code", pattern="hedef_islev")

    assert "notlar.txt" not in sonuc.output


async def test_atlanan_gizli_dosya_sayisi_sonucta_bildirilir(registry, tmp_path):
    (tmp_path / ".env").write_text("hedef_islev=1\n", encoding="utf-8")
    (tmp_path / "config.json").write_text('{"hedef_islev": 1}', encoding="utf-8")
    (tmp_path / "kod.py").write_text("hedef_islev()\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    sonuc = await _calistir(registry, context, "search_code", pattern="hedef_islev")

    assert sonuc.ok and "kod.py" in sonuc.output
    assert "2 dosya" in sonuc.output and "aranmadı" in sonuc.output
    assert ".env" not in sonuc.output and "config.json" not in sonuc.output
