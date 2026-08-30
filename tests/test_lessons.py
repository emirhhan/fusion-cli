def test_adim_isareti_yalniz_bilinen_arayuz_noktalarini_gosterir():
    """`isaret` uydurulamaz: yalnız arayüzde gerçekten var olan noktalar.

    Uydurma bir işaret, kullanıcıya olmayan bir düğmeyi arattırırdı.
    """
    import pytest

    from fusion_cli.appserver.lessons import KNOWN_MARKS, LessonStep, _composer

    with pytest.raises(ValueError, match="Bilinmeyen işaret"):
        LessonStep(
            id="x",
            baslik="x",
            aciklama="x",
            onizleme="x",
            eylem=_composer("merhaba"),
            isaret="olmayan-nokta",
        )

    assert "gorev-kutusu" in KNOWN_MARKS


def test_isaretli_adim_yuke_isareti_tasir():
    from fusion_cli.appserver.lessons import LessonStep, _composer

    adim = LessonStep(
        id="x",
        baslik="x",
        aciklama="x",
        onizleme="x",
        eylem=_composer("merhaba"),
        isaret="gorev-kutusu",
    )

    assert adim.to_payload()["isaret"] == "gorev-kutusu"


def test_isaretsiz_adim_yukunde_isaret_alani_bos_kalir():
    from fusion_cli.appserver.lessons import BUILTIN_LESSONS

    adim = BUILTIN_LESSONS[0].adimlar[0].to_payload()

    assert "isaret" in adim


def test_ilk_ders_arayuzdeki_gercek_noktalari_isaret_eder():
    """Kullanıcı "dersler işe yaramıyor" dedi: adımlar ekranı göstermiyordu."""
    from fusion_cli.appserver.lessons import BUILTIN_LESSONS

    isaretler = [step.isaret for step in BUILTIN_LESSONS[0].adimlar]

    assert any(isaretler), "İlk ders hiçbir arayüz noktasını göstermiyor"
