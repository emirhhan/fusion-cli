"""Takip önerileri: turun KANITINDAN türer, uydurulmaz.

En önemli sözleşme: kanıt yoksa öneri de yok. Boş bir turun altına "testleri
çalıştır" yazmak, yapılmamış işi yapılmış gibi gösteren gürültüdür.
"""

from __future__ import annotations

from fusion_cli.core.followups import TurnEvidence, suggest_followups


def _etiketler(evidence: TurnEvidence, **kwargs: int) -> list[str]:
    return [item.label for item in suggest_followups(evidence, **kwargs)]


def _gerekceler(evidence: TurnEvidence) -> list[str]:
    return [item.reason for item in suggest_followups(evidence)]


def test_kanit_yoksa_oneri_yok():
    """Düz sohbet turunun altına öneri basılmaz."""
    assert suggest_followups(TurnEvidence()) == ()


def test_degisen_dosya_gozden_gecirme_onerir():
    oneriler = suggest_followups(TurnEvidence(changed_files=("src/a.py",)))

    assert oneriler[0].reason == "changed_files"
    assert "a.py" in oneriler[0].label


def test_dosya_ozeti_uzun_listeyi_kisaltir():
    """Rozete sığmayan liste sayıya döner."""
    kanit = TurnEvidence(changed_files=("a.py", "b.py", "c.py", "d.py"))

    assert "ve 2 dosya" in _etiketler(kanit)[0]


def test_dogrulama_komutu_yoksa_calistirma_onerilmez():
    """Çalıştırılacak komut olmadan 'doğrulamayı çalıştır' havada kalır."""
    kanit = TurnEvidence(changed_files=("src/a.py",))

    assert "changed_files+verification_command" not in _gerekceler(kanit)


def test_dogrulama_komutu_varsa_calistirma_onerilir():
    kanit = TurnEvidence(changed_files=("src/a.py",), verification_command="pytest -q")

    assert "changed_files+verification_command" in _gerekceler(kanit)


def test_dusen_dogrulama_onarimi_one_alir():
    """Doğrulama düştüyse sıradaki iş bellidir ve önce gelir."""
    kanit = TurnEvidence(
        changed_files=("src/a.py",),
        verification_command="pytest -q",
        verification_failed=True,
    )
    oneriler = suggest_followups(kanit)

    assert oneriler[0].reason == "verification_failed"
    assert "pytest -q" in oneriler[0].prompt
    # Düşmüş doğrulamayı bir de "çalıştır" diye önermek saçma olurdu.
    assert "changed_files+verification_command" not in [item.reason for item in oneriler]


def test_yanlis_calisma_dizini_her_seyin_onune_gecer():
    """Doğru klasöre geçilmeden başka hiçbir öneri anlamlı değil."""
    kanit = TurnEvidence(
        wrong_workspace=True,
        changed_files=("src/a.py",),
        hit_limit=True,
    )

    assert suggest_followups(kanit)[0].reason == "wrong_workspace"


def test_adim_sinirina_carpan_tur_devami_onerir():
    assert "hit_limit" in _gerekceler(TurnEvidence(hit_limit=True))


def test_basarisiz_arac_adiyla_anilir():
    oneriler = suggest_followups(TurnEvidence(failed_tools=("run_shell",)))

    assert "run_shell" in oneriler[0].label
    assert "run_shell" in oneriler[0].prompt


def test_salt_okur_tur_degisiklik_olmadi_diye_sormaz():
    """Ölçüldü (30 Ekim): salt-okur "anlat" görevinin altında "Neden değişiklik olmadı?"
    çıkıyordu; kimse değişiklik beklemiyordu (`NoFileChanges` rozeti zaten söylüyor)."""
    assert suggest_followups(TurnEvidence(made_no_changes=True)) == ()


def test_salt_okur_turda_basarisiz_okuma_onerilmez():
    """Ölçüldü (30 Ekim): olmayan bir dosyayı yoklayan `read_file` hatası için
    "`read_file` neden başarısız oldu?" öneriliyordu; tur başarıyla bitmişti."""
    kanit = TurnEvidence(made_no_changes=True, failed_tools=("read_file",), ok=True)

    assert suggest_followups(kanit) == ()


def test_salt_okur_turda_proje_dogrulama_komutu_varsa_calistirma_onerilir():
    kanit = TurnEvidence(made_no_changes=True, verification_command="pytest -q")

    oneriler = suggest_followups(kanit)

    assert [item.reason for item in oneriler] == ["read_only+verification_command"]
    assert "pytest -q" in oneriler[0].prompt


def test_basarisiz_tur_basarisiz_araci_yine_onerir():
    kanit = TurnEvidence(made_no_changes=True, failed_tools=("run_shell",), ok=False)

    assert "failed_tools" in _gerekceler(kanit)


def test_degisen_dosya_incelemesi_basarisiz_arac_onerisinden_once_gelir():
    """İşe yarayan öneri (gözden geçir / doğrula) başarısız yoklamanın önüne geçer."""
    kanit = TurnEvidence(
        changed_files=("a.py",), failed_tools=("run_shell",), verification_command="pytest"
    )

    assert _gerekceler(kanit)[0] == "changed_files"
    assert _gerekceler(kanit).index("changed_files") < _gerekceler(kanit).index("failed_tools")


def test_basarisiz_arac_onerisi_eylem_olarak_yazilir():
    etiket = suggest_followups(TurnEvidence(failed_tools=("run_shell",)))[0].label

    assert not etiket.endswith("?")


def test_degisiklik_varsa_yok_diye_sorulmaz():
    """`made_no_changes` ile `changed_files` aynı anda anlamlı değil."""
    kanit = TurnEvidence(made_no_changes=True, changed_files=("a.py",))

    assert "made_no_changes" not in _gerekceler(kanit)


def test_limit_asilmaz():
    kanit = TurnEvidence(
        wrong_workspace=True,
        hit_limit=True,
        failed_tools=("run_shell",),
        changed_files=("a.py",),
        verification_command="pytest",
    )

    assert len(suggest_followups(kanit, limit=2)) == 2
    assert len(suggest_followups(kanit)) == 3


def test_her_onerinin_calistirilabilir_bir_gorevi_var():
    """Rozet tıklanınca gidecek metin boş olamaz."""
    kanit = TurnEvidence(
        wrong_workspace=True,
        hit_limit=True,
        failed_tools=("git",),
        changed_files=("a.py",),
        verification_command="pytest",
        verification_failed=True,
    )

    for oneri in suggest_followups(kanit, limit=10):
        assert oneri.prompt.strip()
        assert oneri.label.strip()
