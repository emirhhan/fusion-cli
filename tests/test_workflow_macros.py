"""Yerleşik iş-akışı makroları (P-050): /simplify, /security-review, /debug, /batch, /doctor.

Claude Code'un paketli becerileriyle aynı adlar; Fusion'da hazır görev metni olarak
çalışırlar. Ölçüldü (31 Ekim): bu adlar kayıt defterinde yoktu, `/doctor` yalnız
alt komut olarak vardı ve `/code-review` tanınmıyordu.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

from fusion_cli.cli.repl import help_view, macros
from fusion_cli.cli.repl.commands import (
    RENDERED_COMMANDS,
    build_registry,
    macro_skill_override,
    renders_itself,
)
from fusion_cli.cli.repl.state import Engine, ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.memory.factory import null_memory
from fusion_cli.ui import messages


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return ReplState(
        config=load_config(source), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


@pytest.mark.parametrize("name", ["simplify", "security-review", "debug", "batch"])
def test_yeni_makrolar_kayit_defterinde_ve_makro_grubunda(name: str) -> None:
    command = build_registry().get(name)
    assert command is not None
    assert command.group == "Makro"
    assert macros.get(name) is not None


def test_code_review_takma_adi_review_makrosunu_cozer() -> None:
    registry = build_registry()
    assert registry.get("code-review") is registry.get("review")


def test_doctor_kendi_ciktisini_basan_komuttur() -> None:
    assert "doctor" in RENDERED_COMMANDS
    command = build_registry().get("doctor")
    assert command is not None and command.group == "Bilgi"


def test_security_review_argumansiz_varsayilan_kapsami_kullanir() -> None:
    macro = macros.get("security-review")
    assert macro is not None
    task = macro.build("")
    assert macros.SECURITY_REVIEW_DEFAULT_SCOPE in task
    # OWASP başlıkları ve rapor biçimi şablonda yer alır.
    for anahtar in ("Sırlar", "Enjeksiyon", "SSRF", "Yol geçişi", "KRİTİK|YÜKSEK|ORTA|DÜŞÜK"):
        assert anahtar in task


def test_security_review_argumani_kapsam_olur() -> None:
    macro = macros.get("security-review")
    assert macro is not None
    task = macro.build("src/api/")
    assert "Kapsam: src/api/" in task
    assert macros.SECURITY_REVIEW_DEFAULT_SCOPE not in task


def test_batch_argumansiz_calismaz(state: ReplState) -> None:
    command = build_registry().get("batch")
    assert command is not None
    assert command.handler(state, "") == messages.REPL_MACRO_NEEDS_ARGUMENT.format(name="batch")
    assert state.pending_task == ""


def test_batch_paralel_alt_ajan_ve_yazma_alani_ister(state: ReplState) -> None:
    command = build_registry().get("batch")
    assert command is not None
    command.handler(state, "tüm print çağrılarını logging'e çevir")
    assert "spawn_agents" in state.pending_task
    assert "yazma_alani" in state.pending_task
    assert state.engine is Engine.AGENT


def test_simplify_hata_avi_yapmaz_ve_review_e_yonlendirir() -> None:
    macro = macros.get("simplify")
    assert macro is not None
    assert "/review" in macro.build("")
    assert "Hata avı" in macro.build("")
    assert "Şunu sadeleştir: src/x.py" in macro.build("src/x.py")


def test_debug_fusion_un_kendisini_teshis_eder_kodu_degistirmez() -> None:
    macro = macros.get("debug")
    assert macro is not None
    task = macro.build("tur hiç cevap vermeden bitiyor")
    assert "fusion doctor --json" in task
    assert "recent_actions" in task
    assert "değiştirme" in task


# --- Kullanıcı skill'i makroyu önceler ---------------------------------------- #


def _skill_yaz(root: Path, name: str, body: str) -> Path:
    path = root / ".claude" / "skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"---\nname: {name}\ndescription: özel\n---\n{body}\n", encoding="utf-8")
    return path


def test_ayni_adli_kullanici_skilli_makronun_onune_eklenir(state: ReplState) -> None:
    path = _skill_yaz(state.root, "security-review", "Önce OWASP ASVS 4.0 listesini uygula.")
    command = build_registry().get("security-review")
    assert command is not None

    result = command.handler(state, "")

    assert state.pending_task.startswith("Önce OWASP ASVS 4.0 listesini uygula.")
    # Yerleşik metin silinmez, kullanıcı kuralından SONRA gelir.
    assert macros.SECURITY_REVIEW_DEFAULT_SCOPE in state.pending_task
    assert str(path) in result


def test_skill_yoksa_makro_metni_degismez(state: ReplState) -> None:
    assert macro_skill_override(state, "simplify") is None
    command = build_registry().get("simplify")
    assert command is not None
    command.handler(state, "")
    macro = macros.get("simplify")
    assert macro is not None
    assert state.pending_task == macro.build("")


def test_bos_govdeli_skill_makroyu_susturmaz(state: ReplState) -> None:
    _skill_yaz(state.root, "debug", "")
    assert macro_skill_override(state, "debug") is None


# --- /doctor REPL ve masaüstü ------------------------------------------------ #


@pytest.mark.asyncio
async def test_doctor_komutu_tani_raporunu_basar(state: ReplState, monkeypatch) -> None:
    from fusion_cli.cli import doctor as doctor_module
    from fusion_cli.config.readiness import Readiness, ReadinessReport

    report = doctor_module.DoctorReport(
        checks=(
            doctor_module.Check(name="Sürüm", value="1.2.3"),
            doctor_module.Check(name="Anahtar", value="yok", ok=False, remedy="/providers add"),
        ),
        readiness=ReadinessReport(Readiness.PARTIALLY_READY, True, False, False, ("hakem yok",)),
    )
    monkeypatch.setattr(doctor_module, "diagnose", lambda *, live=False: report)
    console = Console(record=True, width=100, force_terminal=False, no_color=True)

    await help_view.render("doctor", state, build_registry(), console)

    text = console.export_text()
    assert "Sürüm" in text and "1.2.3" in text
    assert "/providers add" in text
    assert "hakem yok" in text


@pytest.mark.asyncio
async def test_masaustu_doctor_metin_olarak_doner(state: ReplState, monkeypatch) -> None:
    """Masaüstü `komut.calistir /doctor` aynı basıcıdan metin alır; boş dönmez."""
    from fusion_cli.appserver.commands import render_command_text
    from fusion_cli.cli import doctor as doctor_module
    from fusion_cli.config.readiness import Readiness, ReadinessReport

    report = doctor_module.DoctorReport(
        checks=(doctor_module.Check(name="Bellek", value="yazılabilir", ok=True),),
        readiness=ReadinessReport(Readiness.READY, True, True, True, ()),
    )
    monkeypatch.setattr(doctor_module, "diagnose", lambda *, live=False: report)

    text = await render_command_text(build_registry(), state, "doctor")

    assert "Bellek" in text and "yazılabilir" in text


@pytest.mark.asyncio
async def test_masaustu_komut_calistir_doctor_rpc_raporu_dondurur(tmp_path, monkeypatch) -> None:
    """Uçtan uca masaüstü yolu: `komut.calistir {ad: doctor}` RENDERED yolundan metin döner.

    İnceleme (31 Ekim): yalnız `render_command_text` sınanmıştı; AppSession'ın RPC
    yönlendirmesi açıkça sınanmamıştı.
    """
    import json

    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession
    from fusion_cli.cli import doctor as doctor_module
    from fusion_cli.config.readiness import Readiness, ReadinessReport

    monkeypatch.setenv("FUSION_KEYCHAIN", "off")
    report = doctor_module.DoctorReport(
        checks=(doctor_module.Check(name="Sağlayıcı", value="eksik", ok=False, remedy="/login"),),
        readiness=ReadinessReport(Readiness.PARTIALLY_READY, True, False, False, ()),
    )
    monkeypatch.setattr(doctor_module, "diagnose", lambda *, live=False: report)
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    await oturum.handle(Request(id="d1", name="komut.calistir", data={"ad": "doctor"}))

    sonuc = next(
        json.loads(satir)["veri"]
        for satir in reversed(satirlar)
        if json.loads(satir).get("tip") == "sonuc" and json.loads(satir).get("id") == "d1"
    )
    assert sonuc["ok"] is True
    assert "Sağlayıcı" in sonuc["metin"] and "/login" in sonuc["metin"]


def test_doctor_argumansiz_basar_prompt_ile_talimat_denetimine_duser(state: ReplState) -> None:
    """Birleştirme (31 Ekim): `/doctor` kurulum tanısını basar, `/doctor prompt` main'in
    talimat denetimini döndürür; ikisi aynı adı paylaşır, biri ötekini gölgelememeli."""
    assert renders_itself("doctor", "")
    assert not renders_itself("doctor", "prompt")
    assert renders_itself("help", "ne")
    assert not renders_itself("loop", "")

    rapor = build_registry().get("doctor").handler(state, "prompt")  # type: ignore[union-attr]

    assert "fusion doctor" not in rapor
