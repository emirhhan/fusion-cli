"""Takip önerilerinin tur sonuna gerçekten bağlandığı.

`core/followups.py` kuralı test ediyor; bu dosya KÖPRÜYÜ test ediyor: turun
sayaçları kanıta dönüyor mu ve kanıt varsa olay yayınlanıyor mu. İkisi ayrı:
kural doğru olup köprü hiç çağrılmıyor olabilirdi (bu depoda daha önce oldu —
depo haritası modülü yazılmış ama hiçbir yerden çağrılmıyordu).
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.followups import suggest_followups
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.turn_evidence import evidence_from_turn


class _SahteKullanim:
    def __init__(self, name: str, ok: bool) -> None:
        self.name = name
        self.ok = ok


class _SahteSonuc:
    """`AgentOutcome`'ın köprünün okuduğu alanları."""

    def __init__(self, **alanlar: object) -> None:
        self.tool_uses: tuple[_SahteKullanim, ...] = ()
        self.hit_step_limit = False
        self.budget_stopped = False
        self.wrong_workspace = False
        self.made_no_changes = False
        self.ok = True
        for ad, deger in alanlar.items():
            setattr(self, ad, deger)


def _baglam(tmp_path: Path, *degisenler: str) -> ToolContext:
    baglam = ToolContext(root=tmp_path)
    for yol in degisenler:
        hedef = tmp_path / yol
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text("x\n", "utf-8")
        baglam.changes.record(hedef)
    return baglam


def test_degisen_dosyalar_kanita_gecer(tmp_path):
    kanit = evidence_from_turn(_SahteSonuc(), _baglam(tmp_path, "src/a.py"))

    assert any(yol.endswith("a.py") for yol in kanit.changed_files)


def test_basarisiz_arac_adi_kanita_gecer(tmp_path):
    sonuc = _SahteSonuc(
        tool_uses=(_SahteKullanim("read_file", True), _SahteKullanim("run_shell", False))
    )

    kanit = evidence_from_turn(sonuc, _baglam(tmp_path))

    assert kanit.failed_tools == ("run_shell",)
    assert "read_file" in kanit.used_tools


def test_yinelenen_basarisiz_arac_bir_kez_sayilir(tmp_path):
    sonuc = _SahteSonuc(
        tool_uses=(_SahteKullanim("git", False), _SahteKullanim("git", False))
    )

    assert evidence_from_turn(sonuc, _baglam(tmp_path)).failed_tools == ("git",)


def test_butce_durmasi_da_sinir_sayilir(tmp_path):
    """`hit_step_limit` ve `budget_stopped` kullanıcı için aynı şeyi anlatır."""
    kanit = evidence_from_turn(_SahteSonuc(budget_stopped=True), _baglam(tmp_path))

    assert kanit.hit_limit is True


def test_bos_turdan_oneri_cikmaz(tmp_path):
    """Düz sohbet turunun altına öneri basılmaz."""
    kanit = evidence_from_turn(_SahteSonuc(), _baglam(tmp_path))

    assert suggest_followups(kanit) == ()


def test_dogrulama_komutu_kanita_tasinir(tmp_path):
    kanit = evidence_from_turn(
        _SahteSonuc(), _baglam(tmp_path, "src/a.py"), verification_command="pytest -q"
    )

    assert "pytest -q" in [item.prompt for item in suggest_followups(kanit)][-1]


def test_kopru_gercek_bir_turda_oneri_uretir(tmp_path):
    """Uçtan uca: dosya değişmiş ve araç düşmüş bir turdan öneri çıkar."""
    sonuc = _SahteSonuc(tool_uses=(_SahteKullanim("run_shell", False),))

    oneriler = suggest_followups(
        evidence_from_turn(sonuc, _baglam(tmp_path, "src/a.py"), verification_command="pytest")
    )

    gerekceler = [item.reason for item in oneriler]
    assert "failed_tools" in gerekceler
    assert "changed_files" in gerekceler
