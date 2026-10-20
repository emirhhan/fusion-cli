"""Ulaşılamayan kaynak: dürüst başarısızlık, uydurma değil — ve kanıt kapısı bunu ezmez.

Ölçüldü (6 Eylül canlı koşusu, `erisilemeyen-kaynagi-uydurma`): model adresi
denedi, DNS çözülmedi, hiçbir şey uydurmadı ve durumu açıkça anlattı. Kanıt
kapısı yine de "workspace_mutation için başarılı araç çağrısı doğrulanamadı"
deyip modelin AÇIKLAMASINI silip yerine genel bir mesaj koydu. Kullanıcı sebebi
hiç öğrenemedi ve üç koşunun üçü de başarısız sayıldı.

Var olmayan bir adresi kopyalamamak DOĞRU davranıştır; kapının işi iş uydurmayı
yakalamaktır, denemiş ve başaramamış olmayı cezalandırmak değil.
"""

from __future__ import annotations

from fusion_cli.core.constants import UNREACHABLE_RESOURCE_PREFIX
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.loop import run_agent
from fusion_cli.tools.web import web_fetch


def test_cozulemeyen_alan_adi_ulasilamaz_onekiyle_bildirilir(tmp_path):
    sonuc = web_fetch(
        {"url": "https://kesinlikle-var-olmayan-bir-alan-adi-12345.invalid"},
        ToolContext(tmp_path),
    )

    assert not sonuc.ok
    assert sonuc.output.startswith(UNREACHABLE_RESOURCE_PREFIX)


def test_bildirim_uydurmayi_acikca_yasaklar(tmp_path):
    """Uyarı araç SONUCUNA konur: ölçülen davranış, modelin araç sonucuna uymasıdır."""
    sonuc = web_fetch(
        {"url": "https://kesinlikle-var-olmayan-bir-alan-adi-12345.invalid"},
        ToolContext(tmp_path),
    )

    assert "UYDURMA" in sonuc.output
    assert "erişemediğini" in sonuc.output


async def test_ulasilamaz_kaynakta_durust_cevap_ezilmez(monkeypatch, tmp_path):
    """Uçtan uca: model deneyip başaramazsa AÇIKLAMASI korunur.

    Ayırt edici olan şu: aynı görevde araç HİÇ çağrılmasaydı kapı devreye girer
    (bkz. `test_web_build_runs.test_kosu_duvar_yokken_kanit_kapisi_hala_calisir`).
    Buradaki fark, gerçek bir denemenin ulaşılamaz kaynakla karşılaşmasıdır.
    """
    from tests.fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from tests.test_web_build_runs import _kur, _web_deps

    sink = RecordingSink()
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[
                        tool_call(
                            "web_fetch",
                            url="https://kesinlikle-var-olmayan-bir-alan-adi-12345.invalid",
                        )
                    ]
                ),
                model_result("Adrese erişemedim: alan adı çözülemedi. Hiçbir dosya yazmadım."),
                model_result("Adrese erişemedim: alan adı çözülemedi. Hiçbir dosya yazmadım."),
            ]
        ),
    )

    sonuc = await run_agent(
        "https://kesinlikle-var-olmayan-bir-alan-adi-12345.invalid adresindeki siteyi "
        "bu klasöre kopyala",
        _web_deps(tmp_path, sink),
        verify=False,
    )

    assert "İşlem tamamlanmadı" not in sonuc.final_text
    assert "erişemedim" in sonuc.final_text
    assert list(tmp_path.iterdir()) == [], "erişilemeyen sitenin yerine dosya üretildi"
