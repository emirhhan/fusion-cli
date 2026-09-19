"""Tur raporu: başarı beyanı gerçek araç kaydına ve komut çıktısına bağlanır."""

from __future__ import annotations

from fusion_cli.core.evidence import ToolUse
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent.turn_report import build_turn_report


def _shell(command: str, *, exit_code: int, ok: bool | None = None) -> ToolUse:
    return ToolUse(
        name="run_shell",
        ok=exit_code == 0 if ok is None else ok,
        mutating=True,
        arguments={"command": command},
        output=f"(çıkış kodu {exit_code})\nçıktı",
    )


def _write(path: str) -> ToolUse:
    return ToolUse(name="write_file", ok=True, mutating=True, arguments={"path": path})


def _shell_alias(command: str, *, exit_code: int, name: str) -> ToolUse:
    """`run_shell`'in `tools/builtin.py::_ALIASES` içindeki bir takma adıyla
    (`shell`/`bash`/`execute_command`) yapılan çağrı — API modelleri sık sık
    `run_shell` yerine bu adları kullanır."""
    return ToolUse(
        name=name,
        ok=exit_code == 0,
        mutating=True,
        arguments={"command": command},
        output=f"(çıkış kodu {exit_code})\nçıktı",
    )


def test_degisiklik_yoksa_rapor_eklenmez():
    report = build_turn_report((), (), gate=None)

    assert report.render() == ""
    assert report.is_verified is None


def test_degisen_dosyalar_modelin_beyanindan_degil_degisiklik_kaydindan_gelir():
    report = build_turn_report(("a.py", "b.py"), (_write("a.py"), _write("b.py")), gate=None)

    metin = report.render()
    assert "a.py" in metin
    assert "b.py" in metin


def test_son_degisiklikten_sonra_test_calismadiysa_dogrulanmadi_yazar():
    tool_uses = (_write("a.py"),)
    report = build_turn_report(("a.py",), tool_uses, gate=None)

    assert report.is_verified is False
    assert "ÇALIŞTIRILMADI" in report.render()


def test_son_degisiklikten_sonra_basarisiz_test_turu_basarisiz_yapar():
    tool_uses = (_write("a.py"), _shell("pytest -q", exit_code=1))
    report = build_turn_report(("a.py",), tool_uses, gate=None)

    assert report.is_verified is False
    metin = report.render()
    assert "başarısız" in metin
    assert "çıkış 1" in metin


def test_son_degisiklikten_sonra_basarili_test_dogrulandi_yazar():
    tool_uses = (_write("a.py"), _shell("pytest -q", exit_code=0))
    report = build_turn_report(("a.py",), tool_uses, gate=None)

    assert report.is_verified is True
    assert "Doğrulandı" in report.render()


def test_degisiklikten_once_calisan_test_kanit_sayilmaz():
    tool_uses = (_shell("pytest -q", exit_code=0), _write("a.py"))
    report = build_turn_report(("a.py",), tool_uses, gate=None)

    assert report.is_verified is False
    assert "ÇALIŞTIRILMADI" in report.render()


def test_kapi_sonucu_rapora_girer_ve_uyari_tek_yerden_uretilir():
    gate = VerificationResult(ok=False, summary="2 sorun", findings=("boş bağlantı",))
    report = build_turn_report(("a.html",), (_write("a.html"),), gate=gate)

    metin = report.render()
    assert metin.count("DOĞRULAMA GEÇMEDİ") == 1
    assert "boş bağlantı" in metin
    assert report.is_verified is False


def test_kapi_notlari_engellemeden_rapora_eklenir():
    gate = VerificationResult(ok=True, warnings=("erişilebilirlik eksik",))
    tool_uses = (_write("a.html"), _shell("pytest -q", exit_code=0))
    report = build_turn_report(("a.html",), tool_uses, gate=gate)

    metin = report.render()
    assert "erişilebilirlik eksik" in metin
    assert "DOĞRULAMA GEÇMEDİ" not in metin


def test_ayni_komut_birden_cok_run_shell_arasinda_yalniz_son_mutasyondan_sonrakiler_sayilir():
    tool_uses = (
        _write("a.py"),
        _shell("pytest -q", exit_code=1),
        _write("a.py"),
        _shell("pytest -q", exit_code=0),
    )
    report = build_turn_report(("a.py",), tool_uses, gate=None)

    assert report.is_verified is True


def test_run_shell_kendisi_mutasyon_sayilmaz():
    """`run_shell` onay gerektirdiği için mutating=True'dur ama dosya değiştirmez."""
    tool_uses = (_write("a.py"), _shell("pytest -q", exit_code=0))
    report = build_turn_report(("a.py",), tool_uses, gate=None)

    # pytest çağrısı kendi kendinin "sonrası" sayılmamalı; mutasyon a.py yazımıdır.
    assert report.command_runs[0].after_last_mutation is True


def test_davranissal_olmayan_komut_kanit_sayilmaz():
    tool_uses = (_write("a.py"), _shell("ls -la", exit_code=0))
    report = build_turn_report(("a.py",), tool_uses, gate=None)

    assert report.is_verified is False


def test_kanit_eksikligi_turu_basarisiz_saymaz():
    """Hiç test çalışmamış olmak dürüst bir uyarıdır, tur başarısızlığı değil."""
    report = build_turn_report(("a.py",), (_write("a.py"),), gate=None)

    assert report.blocks_success is False


def test_basarisiz_komut_turu_basarisiz_sayar():
    tool_uses = (_write("a.py"), _shell("pytest -q", exit_code=1))
    report = build_turn_report(("a.py",), tool_uses, gate=None)

    assert report.blocks_success is True


def test_dusen_kapi_turu_basarisiz_sayar():
    gate = VerificationResult(ok=False, summary="x", findings=("sorun",))
    report = build_turn_report(("a.py",), (_write("a.py"),), gate=gate)

    assert report.blocks_success is True


def test_run_shell_takma_adiyla_cagrilan_python_pytest_dogrulandi_sayilir():
    """Ölçülen hata (masaüstü uygulaması, API model): model `run_shell`'i `bash`
    takma adıyla çağırdı, komut onaylanıp sıfır çıkış koduyla bitti — ama rapor
    yalnız TAM `run_shell` adına baktığı için bu kanıtı hiç görmedi ve "doğrulama
    komutu ÇALIŞTIRILMADI" dedi. `python -m pytest` gerçek bir davranış komutudur;
    hangi takma adla çağrılırsa çağrılsın "doğrulandı" sayılmalı.
    """
    tool_uses = (_write("a.py"), _shell_alias("python -m pytest", exit_code=0, name="bash"))
    report = build_turn_report(("a.py",), tool_uses, gate=None)

    assert report.is_verified is True
    assert "Doğrulandı" in report.render()


def test_run_shell_takma_adiyla_calisan_davranissal_olmayan_komut_kanit_sayilmaz():
    """Takma ad tanınsa bile komutun kendisi davranış KANITLAMIYORSA (ör. `ls`,
    `cat`) rapor hâlâ "kanıt yok" demeli — takma ad tanıma, komut sınıflandırma
    kuralını gevşetmez."""
    tool_uses = (_write("a.py"), _shell_alias("ls -la", exit_code=0, name="shell"))
    report = build_turn_report(("a.py",), tool_uses, gate=None)

    assert report.is_verified is False
    assert "ÇALIŞTIRILMADI" in report.render()
