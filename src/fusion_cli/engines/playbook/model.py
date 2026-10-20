"""Playbook veri modeli — deterministik bir akışın tanımı ve sonucu.

Bir playbook üç parçadan oluşur: ön-koşul (tetikleyiciler), sıralı adımlar ve başarı
doğrulama komutları (`checks`). Adımın isteğe bağlı bir geri-alma komutu vardır;
`checks` başarısızsa çalıştırılmış adımlar TERS sırada geri alınır.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PlaybookStep:
    """Tek bir deterministik adım: ne yaptığı, komutu ve (varsa) geri-alma komutu."""

    description: str
    command: str
    #: Geri-alma komutu; boş = bu adımın geri alınacak bir yan etkisi yok (idempotent).
    rollback: str = ""


@dataclass(frozen=True, slots=True)
class Playbook:
    """Ön-koşulu eşleşince çalıştırılan deterministik akış."""

    id: str
    description: str
    #: İstekte bunlardan HERHANGİ biri geçerse playbook eşleşir (kaba ön-koşul).
    triggers: tuple[str, ...]
    steps: tuple[PlaybookStep, ...]
    #: Başarı doğrulaması: her komut 0 dönmeli. Boşsa adımların bitmesi başarı sayılır.
    checks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlaybookResult:
    """Bir playbook çalıştırmasının sonucu."""

    ok: bool
    #: Çalıştırılan adım açıklamaları (sırayla).
    ran_steps: tuple[str, ...] = field(default_factory=tuple)
    #: İnsan-okur özet (başarı ya da ilk başarısızlık nedeni).
    summary: str = ""
    #: `checks`/adım başarısızlığında geri alma yapıldı mı.
    rolled_back: bool = False
