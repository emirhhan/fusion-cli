"""Model aracın adını farklı tahmin ederse tur harcanmaz.

Ölçüldü (6 Eylül canlı koşusu, `mevcut-projeye-uy`): model üç koşunun ikisinde
`shell` çağırdı ve "bilinmeyen araç; kullanılabilir araçlar: …" cevabını aldı; o
tur tamamen boşa gitti. Doğru adı bilmemek bir yetenek eksikliği değil,
isimlendirme tercihidir — kayıt defteri bunu kendi çözebiliyorken tura mal
etmenin gerekçesi yok.

Takma ad ŞEMADA sunulmaz: modele iki isim göstermek seçim kalabalığı üretir.
Yalnızca çalıştırma tarafında tanınır.
"""

from __future__ import annotations

from fusion_cli.core.tools import ToolFamily, tool_family
from fusion_cli.tools import build_registry

#: Ad → gerçek araç. Ölçülen tahminler ve yakın komşuları.
BEKLENEN = {
    "shell": "run_shell",
    "bash": "run_shell",
    "execute_command": "run_shell",
    "list_files": "list_dir",
    "create_file": "write_file",
}


def test_tahmin_edilen_adlar_calistirilabilir():
    registry = build_registry()

    for takma, gercek in BEKLENEN.items():
        arac = registry.get(takma)
        assert arac is not None, f"{takma} tanınmıyor"
        assert arac.run is registry.get(gercek).run


def test_takma_adlar_semada_sunulmaz():
    """Modele TEK isim gösterilir; kalabalık seçim hatası üretir."""
    sunulan = {s["function"]["name"] for s in build_registry().schemas()}

    assert not (set(BEKLENEN) & sunulan)


def test_takma_adlar_dogru_aileye_dusuyor():
    """Aile bilinmezse adım kapsamı takma adı 'dış araç' sayıp ENGELLER.

    Bu, çözülen sorunu başka bir kılıkta geri getirirdi.
    """
    assert tool_family("shell") is ToolFamily.SHELL
    assert tool_family("create_file") is ToolFamily.FILES
    for takma in BEKLENEN:
        assert tool_family(takma) is not ToolFamily.EXTERNAL


def test_takma_ad_mutasyon_bayragini_korur():
    """`create_file` yazma yapar; onay ve kapasite kapıları bunu görmeli."""
    registry = build_registry()

    assert registry.get("create_file").mutating
    assert not registry.get("list_files").mutating
