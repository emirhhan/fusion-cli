"""Tur bittiğinde gösterilecek "sıradaki adım" önerileri — saf üretici.

Faz 5'te kararlaştırılan kısıt burada uygulanır: **öneri üretmek için YENİ BİR
MODEL ÇAĞRISI AÇILMAZ.** Öneriler turun kendi kanıtından türetilir — değişen
dosyalar, başarısız araçlar, çarpılan bütçe sınırı. Bu hem ücretsiz hem de
dürüst: model bir şey "önermez", tur ne olduysa o söylenir.

İkinci kural: **kanıt yoksa öneri de yok.** Boş bir turun altına "testleri
çalıştır" yazmak, yapılmamış işi yapılmış gibi gösteren yalan başarıdan farksız
bir gürültüdür (bkz. `evals/metrics.py::TaskResult.false_success`). Bu yüzden
her kuralın bir kanıt koşulu vardır ve hiçbiri sabit metin döndürmez.

Saf modüldür: ağ, dosya sistemi ve saat yoktur; doğrudan test edilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Followup", "TurnEvidence", "suggest_followups"]

#: Aynı anda gösterilecek en fazla öneri. Üçten fazlası seçim değil, liste olur.
DEFAULT_LIMIT = 3

#: Öneride adı geçirilecek en fazla dosya. Uzun liste rozete sığmaz.
_MAX_NAMED_FILES = 2


@dataclass(frozen=True, slots=True)
class TurnEvidence:
    """Bir turun önerilere girdi olan gözlemleri.

    `AgentOutcome`'dan AYRI tutulur: `core` katmanı `engines`'e bakamaz ve
    öneriler CLI, masaüstü ve testlerde aynı girdiyle üretilebilmelidir.
    """

    #: Turda değişen dosya yolları (göreli).
    changed_files: tuple[str, ...] = ()
    #: Başarısız olan araçların adları.
    failed_tools: tuple[str, ...] = ()
    #: Tur bir bütçe/adım sınırına çarparak mı bitti?
    hit_limit: bool = False
    #: Görevdeki dosyalar bulunamadı — muhtemelen yanlış çalışma dizini.
    wrong_workspace: bool = False
    #: Araç çalıştı ama hiçbir şey değişmedi.
    made_no_changes: bool = False
    #: Tur temiz bitti mi?
    ok: bool = True
    #: Projenin kendi doğrulama komutu çalıştı ve DÜŞTÜ mü?
    verification_failed: bool = False
    #: Projenin doğrulama komutu (varsa). Yoksa "testleri çalıştır" önerilmez —
    #: çalıştırılacak bir komut olmadan öneri havada kalır.
    verification_command: str = ""
    #: Turda kullanılan araç adları (kanıt için; sıra önemli değil).
    used_tools: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Followup:
    """Tek bir öneri: kullanıcıya görünen etiket ve tıklanınca gidecek görev."""

    #: Rozette yazan kısa metin.
    label: str
    #: Seçilince composer'a/tura gidecek tam görev metni.
    prompt: str
    #: Öneriyi doğuran kanıt. Teşhis ve test içindir, kullanıcıya gösterilmez.
    reason: str


def _dosya_ozeti(yollar: tuple[str, ...]) -> str:
    """Değişen dosyaları rozete sığacak biçimde yaz."""
    adlar = [yol.rsplit("/", 1)[-1] for yol in yollar[:_MAX_NAMED_FILES]]
    kalan = len(yollar) - len(adlar)
    if kalan > 0:
        return f"{', '.join(adlar)} ve {kalan} dosya"
    return ", ".join(adlar)


def suggest_followups(
    evidence: TurnEvidence, *, limit: int = DEFAULT_LIMIT
) -> tuple[Followup, ...]:
    """Turun kanıtından sıradaki adımları üret; kanıt yoksa boş döner.

    Sıra ÖNEMLİDİR: en üstteki öneri turun en acil eksiğini kapatır. Kullanıcı
    ilk rozeti okumadan tıklayabilmeli.
    """
    oneriler: list[Followup] = []

    # 1) Yanlış çalışma dizini her şeyin önüne geçer: başka hiçbir öneri
    #    doğru klasöre geçilmeden anlamlı değil.
    if evidence.wrong_workspace:
        oneriler.append(
            Followup(
                label="Doğru proje klasörünü seç",
                prompt="Görevdeki dosyalar bu klasörde bulunamadı. Doğru proje klasörü hangisi?",
                reason="wrong_workspace",
            )
        )

    # 2) Doğrulama DÜŞTÜYSE bir sonraki iş bellidir.
    if evidence.verification_failed and evidence.verification_command:
        oneriler.append(
            Followup(
                label="Düşen doğrulamayı onar",
                prompt=(
                    f"`{evidence.verification_command}` düştü. Sebebini bul ve düzelt, "
                    "sonra aynı komutu tekrar çalıştır."
                ),
                reason="verification_failed",
            )
        )

    # 3) Bütçe sınırına çarpan tur yarım kaldı: devam etmek kullanıcının
    #    muhtemelen isteyeceği ilk şey.
    if evidence.hit_limit:
        oneriler.append(
            Followup(
                label="Kaldığın yerden devam et",
                prompt="Tur adım sınırına takıldı. Kaldığın yerden devam et.",
                reason="hit_limit",
            )
        )

    # 4) Başarısız araç varsa nedenini sormak mantıklı.
    if evidence.failed_tools:
        arac = evidence.failed_tools[0]
        oneriler.append(
            Followup(
                label=f"`{arac}` neden başarısız oldu?",
                prompt=f"Turda `{arac}` başarısız oldu. Nedenini araştır ve düzelt.",
                reason="failed_tools",
            )
        )

    # 5) Dosya değiştiyse: önce gözden geçirme, sonra (komut varsa) doğrulama.
    if evidence.changed_files:
        oneriler.append(
            Followup(
                label=f"Değişiklikleri gözden geçir ({_dosya_ozeti(evidence.changed_files)})",
                prompt=(
                    "Bu turda yaptığın değişiklikleri gözden geçir ve riskli bir yer "
                    "varsa söyle."
                ),
                reason="changed_files",
            )
        )
        if evidence.verification_command and not evidence.verification_failed:
            oneriler.append(
                Followup(
                    label="Doğrulamayı çalıştır",
                    prompt=f"`{evidence.verification_command}` komutunu çalıştır ve sonucu bildir.",
                    reason="changed_files+verification_command",
                )
            )

    # 6) Araç çalıştı ama hiçbir şey değişmediyse bu bir soru işaretidir.
    if evidence.made_no_changes and not evidence.changed_files:
        oneriler.append(
            Followup(
                label="Neden değişiklik olmadı?",
                prompt="Bu turda hiçbir dosya değişmedi. Nedenini açıkla; iş zaten yapılmış mıydı?",
                reason="made_no_changes",
            )
        )

    return tuple(oneriler[:limit])
