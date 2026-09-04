

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
