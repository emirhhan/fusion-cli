"""Taklit araç sözleşmesi var olan dosyayı KISMEN değiştirmeyi öğretiyor mu?

Ölçüldü (Gemini web, dört dosyalık görev): model dört dosyanın da TAMAMINI
yeniden yazdı. Testler geçti, içerik kaybı olmadı — ama boş satır düzeni bozuldu
ve projenin ruff hatası 1'den 3'e çıktı.

Sebep modelde değildi. Sözleşmedeki tek mutasyon örneği `write_file` idi ve
`edit_file`'ın çok satırlı hâli (tek çağrıda iki payload) hiç gösterilmemişti.
Mekanizma zaten çalışıyordu; model bilmediği bir biçimi kullanamazdı.
"""

from __future__ import annotations

import json

from fusion_cli.core.tool_emulation import (
    PAYLOAD_CLOSE,
    PAYLOAD_OPEN,
    PAYLOAD_SENTINEL,
    parse_tool_calls,
    render_tool_instructions,
)
from fusion_cli.tools import build_registry


def _payload(payload_id: str, body: str) -> str:
    return "\n".join(
        [
            f'{PAYLOAD_OPEN} id="{payload_id}"',
            "```python",
            PAYLOAD_SENTINEL,
            body,
            "```",
            PAYLOAD_CLOSE,
        ]
    )


# --- Mekanizma: bir çağrıda iki payload ---------------------------------------- #


def test_tek_cagrida_iki_payload_ayri_alanlara_baglanir() -> None:
    ham = "\n".join(
        [
            _payload("eski-1", "def f():\n    return 1"),
            _payload("yeni-1", "def f():\n    return 2"),
            "FUSION_TOOL_CALL",
            json.dumps(
                {
                    "name": "edit_file",
                    "arguments": {
                        "path": "a.py",
                        "old": {"$ref": "eski-1"},
                        "new": {"$ref": "yeni-1"},
                    },
                }
            ),
            "FUSION_TOOL_CALL_END",
        ]
    )

    parsed = parse_tool_calls(ham)

    assert not parsed.errors, parsed.errors
    arguments = json.loads(parsed.calls[0].arguments)
    assert arguments["old"] == "def f():\n    return 1"
    assert arguments["new"] == "def f():\n    return 2"


# --- Sözleşme: modele GÖSTERİLİYOR mu? ----------------------------------------- #


def _instructions() -> str:
    return render_tool_instructions(build_registry().schemas())


def test_sozlesme_replace_range_ornegi_icerir() -> None:
    """Ana kısmi-edit örneği replace_range V2 olmalı."""
    metin = _instructions()

    assert '"name":"replace_range"' in metin
    assert "replace_range" in metin
    assert "Eski içeriği" in metin or "ESKİ içeriği" in metin


def test_sozlesmedeki_edit_ornegi_kendi_ayristiricimizdan_gecer() -> None:
    """Örnek ile ayrıştırıcı ayrışırsa modele yanlış biçim öğretmiş oluruz."""
    from fusion_cli.core.tool_emulation import EDIT_EXAMPLE

    parsed = parse_tool_calls(EDIT_EXAMPLE)

    assert not parsed.errors, parsed.errors
    assert parsed.calls[0].name == "edit_file"
    arguments = json.loads(parsed.calls[0].arguments)
    assert arguments["old"] != arguments["new"]
    assert "$ref" not in parsed.calls[0].arguments, "referanslar çözülmüş olmalı"


def test_sozlesme_var_olan_dosyada_replace_range_tercihini_soyler() -> None:
    metin = _instructions()

    assert "replace_range kullan" in metin
    assert "write_file DEĞİL" in metin


# --- Takma adlar: çalışır ama listelenmez --------------------------------------- #


def test_takma_adlar_modele_ayri_arac_diye_sunulmaz() -> None:
    """`view_file` ile `read_file` aynı şeydir; ikisini de listelemek seçim değil
    kararsızlık üretir (ölçüldü: model ikisini dönüşümlü kullanıp takıldı)."""
    sunulan = {
        schema["function"]["name"]  # type: ignore[index]
        for schema in build_registry().schemas()
    }

    assert "read_file" in sunulan
    assert "view_file" not in sunulan
    assert "grep_search" not in sunulan
    assert "read_url_content" not in sunulan


def test_takma_adlar_yine_de_calisir() -> None:
    """Sunmamak yasaklamak değildir: model yine de çağırırsa hata almamalı."""
    registry = build_registry()

    for alias, target in (
        ("view_file", "read_file"),
        ("grep_search", "search_code"),
        ("read_url_content", "web_fetch"),
    ):
        tool = registry.get(alias)
        assert tool is not None, f"takma ad kaybolmuş: {alias}"
        assert tool.run is registry.get(target).run  # type: ignore[union-attr]


def test_sunulan_liste_izin_verilenlerle_daraltilinca_da_takma_ad_sizmaz() -> None:
    sunulan = {
        schema["function"]["name"]  # type: ignore[index]
        for schema in build_registry().schemas(["read_file", "view_file"])
    }

    assert sunulan == {"read_file"}


# --- Kesilen yanıt: payload var, çağrı yok ------------------------------------ #
#
# Ölçüldü (Gemini web, üç koşu): tutarsızlığın kaynağı model tercihi değil, yanıt
# uzunluğuydu. Koşu 2'de model DOĞRU şeyi yaptı — dört dosya için çok payload'lı
# edit_file üretmeye başladı — ama yanıt 5570 karakterde kesildi ve çağrı bloğu hiç
# gelmedi. Genel "payload kullanılmadı" hatası ne olduğunu anlatmadığı için model
# write_file ile tam dosya yazmaya düştü ve kodu bozdu.
#
# Başarılı iki koşu (6 ve 11 edit_file) yanıt başına TEK çağrı yapmıştı.


def test_cagri_bloguna_varmadan_kesilen_yanit_teshis_edilir() -> None:
    parsed = parse_tool_calls(_payload("eski-1", "def f():\n    return 1"))

    assert not parsed.calls
    (hata,) = parsed.errors
    assert "kesildi" in hata
    # Hata eyleme dönüştürülebilir olmalı (RULES.md "Hata Yönetimi").
    assert "TEK bir araç çağrısı" in hata
    assert "tamamını yeniden yazmaya KALKMA" in hata


def test_cagri_varken_artan_payload_kesilme_sayilmaz() -> None:
    """Çağrı geldiyse yanıt kesilmemiştir; fazla payload ayrı bir hatadır."""
    ham = "\n".join(
        [
            _payload("kullanilan", "x = 1"),
            _payload("artan", "y = 2"),
            "FUSION_TOOL_CALL",
            json.dumps(
                {
                    "name": "write_file",
                    "arguments": {"path": "a.py", "content": {"$ref": "kullanilan"}},
                }
            ),
            "FUSION_TOOL_CALL_END",
        ]
    )

    parsed = parse_tool_calls(ham)

    assert parsed.calls
    assert any("payload kullanılmadı: artan" in hata for hata in parsed.errors)
    assert not any("kesildi" in hata for hata in parsed.errors)


def test_sozlesme_tek_cagri_kuralini_degistiricilerle_sinirlar() -> None:
    """Tek-çağrı kuralı YALNIZCA değiştirici araçlar için.

    Kural her araca uygulanınca keşfin maliyeti dört katına çıkıyordu: dizin
    listelemek + üç dosya okumak dört tur yiyor, tur bütçesi yazmaya sıra
    gelmeden bitiyordu. Okuma çağrıları kısa tek satırlık JSON'dur; yanıtın
    kesilme riski yoktur.
    """
    metin = _instructions()

    assert "EN FAZLA BİR DEĞİŞTİRİCİ çağrı" in metin
    assert "BİRDEN ÇOK yapabilirsin" in metin
    assert "replace_range" in metin


# --- ölü kilit: edit tutmuyor, write engelli ------------------------------- #
#
# Ölçüldü (gerçek koşu): `edit_file` üç kez "'old' bulunamadı" verdi, model
# `write_file`'a kaçtı ve KOŞULSUZ engellendi, tekrar `edit_file` denedi, yine
# tutmadı ve tur "3 turdur ilerleme yok" ile öldü. Model doğru dosyayı doğru
# niyetle hedeflemişti; çıkışı olmayan bir kapıya çarptı.


def _durum(basarisiz: int):
    from fusion_cli.engines.agent.loop import _State

    return _State(failed_mutations_in_row=basarisiz)


def _deps_for(tmp_path, okundu: bool):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
    from fusion_cli.engines.agent.loop import AgentDeps

    from .fakes import AlwaysApprove, RecordingSink, make_config

    hedef = tmp_path / "cart.js"
    hedef.write_text("x = 1\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)
    if okundu:
        context.fully_read.add(hedef.resolve())

    class _P:
        def publish(self, event):
            pass

    return AgentDeps(
        config=make_config(),
        publisher=_P(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=context,
    ), RecordingSink()


def _web_execution():
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy

    return ExecutionPolicy(is_web=True)


def test_var_olan_dosyaya_toptan_yazma_normalde_engellenir(tmp_path):
    from fusion_cli.engines.agent.loop import _targeted_edit_required

    deps, _ = _deps_for(tmp_path, okundu=True)

    hatalar = _targeted_edit_required(
        "write_file", {"path": "cart.js"}, deps, _web_execution(), _durum(0)
    )

    assert hatalar and "replace_range" in hatalar[0]


def test_duzenleme_tekrar_tekrar_dustuyse_ve_dosya_okunduysa_yazmaya_izin_verilir(tmp_path):
    from fusion_cli.engines.agent.loop import _targeted_edit_required

    deps, _ = _deps_for(tmp_path, okundu=True)

    assert not _targeted_edit_required(
        "write_file", {"path": "cart.js"}, deps, _web_execution(), _durum(2)
    )


def test_dosya_okunmadiysa_yazma_yine_engellenir(tmp_path):
    """Kuralın gerekçesi kör yazmayı önlemek; içerik görülmediyse gerekçe durur."""
    from fusion_cli.engines.agent.loop import _targeted_edit_required

    deps, _ = _deps_for(tmp_path, okundu=False)

    assert _targeted_edit_required(
        "write_file", {"path": "cart.js"}, deps, _web_execution(), _durum(4)
    )


async def test_dongu_notu_yazma_cikisini_kapatmaz(tmp_path):
    """Not "write_file ile yaz" diyorsa o yol AÇIK kalmalı.

    Ölçüldü: not ateşlerken başarısız-düzenleme sayacı sıfırlanıyordu; toptan
    yazma engelinin kalkması aynı sayaca baktığı için model tavsiyeye uyduğu anda
    kapı yeniden kapanıyor ve tur ölü kilide düşüyordu.
    """
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import loop as agent_loop
    from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
    from fusion_cli.engines.agent.loop import AgentDeps, run_agent

    from .fakes import (
        AlwaysApprove,
        RecordingSink,
        ScriptedProvider,
        make_config,
        model_result,
        tool_call,
    )

    hedef = tmp_path / "cart.js"
    hedef.write_text("function total() { return 0; }\n", encoding="utf-8")
    yeni_icerik = "function total() { return 1; }"

    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("read_file", path="cart.js")]),
            model_result(tool_calls=[tool_call("edit_file", path="cart.js", old="YOK-1", new="b")]),
            model_result(tool_calls=[tool_call("edit_file", path="cart.js", old="YOK-2", new="d")]),
            model_result(tool_calls=[tool_call("edit_file", path="cart.js", old="YOK-3", new="f")]),
            model_result(tool_calls=[tool_call("write_file", path="cart.js", content=yeni_icerik)]),
            model_result("Dosya yeniden yazıldı: `cart.js`."),
        ]
    )
    monkey_target = agent_loop
    original = monkey_target.build_provider
    monkey_target.build_provider = lambda *a, **k: provider
    try:
        sink = RecordingSink()

        class _P:
            def publish(self, event):
                sink.handle(event)

        deps = AgentDeps(
            config=make_config(runtime={"agent_max_idle_rounds": 10}),
            publisher=_P(),
            policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
            tool_context=ToolContext(root=tmp_path),
        )
        deps.execution = None
        sonuc = await run_agent("cart.js'yi düzelt", deps)
    finally:
        monkey_target.build_provider = original

    assert "return 1" in hedef.read_text(encoding="utf-8"), "toptan yazma yine engellendi"
    assert sonuc.mutating_tool_calls_made == 1
