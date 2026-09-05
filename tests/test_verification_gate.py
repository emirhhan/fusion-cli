async def test_zaman_asiminda_komutun_soyledigi_kaybolmaz():
    """Zaman aşımı öncesi üretilen çıktı EN DEĞERLİ tanıdır; atılmamalı.

    Ölçüldü: bozuk bir Godot projesinde `godot --headless --path . --quit`
    gerçek sebebi basıyor (`Can't run project: no main scene defined in the
    project`) ve SONRA asılı kalıyor. Kapı yalnızca "zaman aşımına uğradı"
    diyordu; model neyi düzelteceğini öğrenemiyordu.
    """
    from fusion_cli.engines.agent.verification import CommandVerifier

    # İşaret komut METNİNDE geçmemeli: geçseydi test, çıktı taşınmasa da
    # zaman aşımı mesajındaki komut yankısı yüzünden geçerdi.
    komut = "python3 -c \"print('SEBEP' + 'X' * 3)\"; sleep 30"
    kapi = CommandVerifier((komut,), cwd=".", timeout_s=2)

    sonuc = await kapi.verify()

    assert sonuc.ok is False
    birlesik = sonuc.summary + " ".join(sonuc.findings)
    assert "zaman aşımı" in birlesik
    assert "SEBEPXXX" in birlesik, "asılmadan önceki çıktı taşınmalı"


async def test_sifir_cikis_kodu_motorun_hata_bildirimini_gizlemez():
    """Godot bozuk script'te ve çalışma zamanı hatasında `0` döndürebiliyor.

    Ölçüldü: `godot --headless --path . --quit` `SCRIPT ERROR: Parse Error`
    bastıktan sonra sıfırla çıktı; kapı bunu "komut başarıyla çalıştı" sayıp
    kabul verdi. Motor kendi hatasını söylerken çıkış kodunun sessizliğine
    güvenmek, kapıyı tam da işe yarayacağı yerde kör eder.
    """
    from fusion_cli.core.evidence import EvidenceStatus
    from fusion_cli.engines.agent.verification import CommandVerifier

    komut = "godot() { echo 'SCRIPT ERROR: Parse Error: Identifier not found'; }; godot"
    kapi = CommandVerifier((komut,), cwd=".", timeout_s=5)

    sonuc = await kapi.verify()

    assert sonuc.ok is False
    assert "Parse Error" in " ".join(sonuc.findings)
    assert sonuc.evidence[0].status is EvidenceStatus.FAILED


async def test_hatasiz_godot_cikisi_kapiyi_dusurmez():
    """İşaret taraması yalnız motorun hata satırında tetiklenmeli."""
    from fusion_cli.core.evidence import EvidenceStatus
    from fusion_cli.engines.agent.verification import CommandVerifier

    komut = "godot() { echo 'Godot Engine v4.3 - godotengine.org'; }; godot --headless --quit"
    kapi = CommandVerifier((komut,), cwd=".", timeout_s=5)

    sonuc = await kapi.verify()

    assert sonuc.ok is True
    assert sonuc.evidence[0].status is EvidenceStatus.PASSED
