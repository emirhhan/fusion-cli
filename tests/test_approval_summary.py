import pytest

from fusion_cli.appserver.approval_summary import approval_summary


@pytest.mark.parametrize(
    ("arac", "argumanlar", "baslik", "hedef"),
    [
        ("run_shell", {"command": "npm test"}, "Bu komut çalıştırılsın mı?", "npm test"),
        ("bash", {"command": "git push"}, "Bu komut çalıştırılsın mı?", "git push"),
        ("write_file", {"path": "src/a.ts", "content": "x"}, "Bu dosya yazılsın mı?", "src/a.ts"),
        ("edit_file", {"path": "b.py"}, "Bu dosya düzenlensin mi?", "b.py"),
        (
            "chrome_navigate",
            {"url": "https://ads.google.com"},
            "Tarayıcıda bu işlem yapılsın mı?",
            "https://ads.google.com",
        ),
        ("desktop_type", {"text": "merhaba"}, "Bilgisayarında bu işlem yapılsın mı?", "merhaba"),
        (
            "novamira__update_product",
            {"id": 5},
            "novamira üzerinde “update_product” çalıştırılsın mı?",
            "",
        ),
        ("gizemli", {}, "“gizemli” aracı çalıştırılsın mı?", ""),
    ],
)
def test_izin_karti_insan_dilinde_baslik_ve_hedef_verir(arac, argumanlar, baslik, hedef):
    assert approval_summary(arac, argumanlar) == (baslik, hedef)


def test_yetenek_gecidinde_calisacak_yetenek_ve_parametreler_gosterilir():
    baslik, hedef = approval_summary(
        "motogate__mcp-adapter-execute-ability",
        {"ability_name": "woocommerce/product-update", "parameters": {"id": 5, "fiyat": 100}},
    )
    assert baslik == "motogate üzerinde “woocommerce/product-update” çalıştırılsın mı?"
    assert '"fiyat": 100' in hedef


def test_tarayici_tiklamasinda_ogenin_adi_ref_yerine_gosterilir():
    """Ölçüldü (27 Eylül): kart yalnız "e52" gösteriyordu; kullanıcı neye
    tıklanacağını bilmeden karar veriyordu."""
    assert approval_summary("chrome_click", {"ref": "e52"}, element="Yorum yap") == (
        "Bu öğeye tıklansın mı?",
        "“Yorum yap” öğesine tıklanacak",
    )
    assert approval_summary("chrome_click", {"ref": "e52"}) == ("Bu öğeye tıklansın mı?", "e52")
    assert approval_summary("chrome_action", {"action": "key", "value": "Enter"}) == (
        "Bu tuşa basılsın mı?",
        "Enter (açık formu gönderebilir)",
    )


async def test_prompter_tiklanacak_ogenin_adini_kopruden_alir():
    import asyncio
    import json

    from fusion_cli.appserver.bridges import PendingQuestions, ProtocolPrompter
    from fusion_cli.core.tools import ToolEffect
    from fusion_cli.engines.agent.approval import ApprovalRequest
    from fusion_cli.tools.builtin import build_registry

    satirlar: list[str] = []
    bekleyen = PendingQuestions()
    prompter = ProtocolPrompter(
        satirlar.append, bekleyen, element_name=lambda ref: "Paylaş" if ref == "e7" else None
    )
    arac = build_registry().get("chrome_click")
    istek = ApprovalRequest(
        tool=arac, args={"ref": "e7"}, danger=None, effect=ToolEffect.REMOTE_WRITE
    )
    gorev = asyncio.create_task(prompter.confirm(istek))
    await asyncio.sleep(0)
    soru = json.loads(satirlar[-1])
    assert soru["veri"]["hedef"] == "“Paylaş” öğesine tıklanacak"
    bekleyen.resolve(soru["id"], {"secim": "deny"})
    await gorev
