"""Uygulama içi ders kataloğu — tasarım §12 "İlk açılış ve dersler".

Dersler ayrı bir doküman okuyucusu DEĞİLDİR: her adım kullanıcının gerçek
çalışma alanında küçük ve geri alınabilir bir görevle ilerler. Bu yüzden her
adımın `eylem` alanı yalnız uygulamanın ZATEN sunduğu bir yüzeyi işaret eder —
composer'a hazır görev metni koymak ya da var olan bir sekmeyi öne getirmek.
`eylem` kendi başına dosya YAZMAZ, komut ÇALIŞTIRMAZ, ağa ÇIKMAZ; kullanıcı
göndermeden/onaylamadan hiçbir şey çalışmaz (mevcut onay ve geri alma
sözleşmesi değişmez, bkz. `engines/agent/approval.py`).

Bu modül yalnız METADATA taşır (`providers/registry.py`'deki `BUILTIN_PROVIDERS`
ile aynı desen): sabit bir ders tanımı listesi. Modül seviyesinde iş yapılmaz;
import anında dosya/ağ/süreç erişimi yoktur.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

#: Bir eylemin işaret edebileceği güvenli yüzeyler. Yeni bir tür eklemek
#: uygulamanın gerçekten sunduğu yeni bir yüzey demektir; komut/dosya taşıyan
#: bir tür asla eklenmez.
ActionKind = Literal["composer", "sekme"]

#: `eylem.hedef` yalnız bu bilinen sekme adlarından biri olabilir — hepsi
#: protokolde zaten var olan istek ön ekleridir (bkz. `session.py::_dispatch`).
KNOWN_TABS = ("proje", "surec", "yetenek", "kontrol", "gecmis")


@dataclass(frozen=True)
class LessonAction:
    """Bir ders adımının işaret ettiği tek güvenli yüzey.

    `tur="composer"` iken `gorev` metni composer'a hazır olarak konur; kullanıcı
    göndermeden hiçbir şey çalışmaz. `tur="sekme"` iken yalnız var olan bir
    sekme (`KNOWN_TABS`) öne getirilir. İki durumda da komut satırı, dosya
    yolu ya da ağ adresi taşınmaz.
    """

    tur: ActionKind
    gorev: str | None = None
    hedef: str | None = None

    def to_payload(self) -> dict[str, Any]:
        if self.tur == "composer":
            return {"tur": self.tur, "gorev": self.gorev or ""}
        return {"tur": self.tur, "hedef": self.hedef or ""}


def _composer(gorev: str) -> LessonAction:
    """Composer'a hazır görev metni koyan güvenli eylem üret."""
    return LessonAction(tur="composer", gorev=gorev)


def _sekme(hedef: str) -> LessonAction:
    """Var olan bir sekmeyi öne getiren güvenli eylem üret."""
    if hedef not in KNOWN_TABS:
        raise ValueError(f"Bilinmeyen sekme hedefi: {hedef}")
    return LessonAction(tur="sekme", hedef=hedef)


@dataclass(frozen=True)
class LessonStep:
    """Bir dersin tek adımı: başlık, açıklama ve tek güvenli eylem."""

    id: str
    baslik: str
    aciklama: str
    eylem: LessonAction

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "baslik": self.baslik,
            "aciklama": self.aciklama,
            "eylem": self.eylem.to_payload(),
        }


@dataclass(frozen=True)
class Lesson:
    """Bir ders: kimlik, başlık, özet ve sıralı adımlar."""

    id: str
    baslik: str
    ozet: str
    adimlar: tuple[LessonStep, ...]

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "baslik": self.baslik,
            "ozet": self.ozet,
            "adim_sayisi": len(self.adimlar),
        }

    def to_detail(self) -> dict[str, Any]:
        return {
            "ok": True,
            "id": self.id,
            "baslik": self.baslik,
            "ozet": self.ozet,
            "adimlar": [step.to_payload() for step in self.adimlar],
        }


#: Tasarımdaki sekiz ders (§12), sabit sırayla. Sıra kullanıcının önerilen
#: öğrenme yoluyla eşleşir; rastgele karıştırılmaz.
BUILTIN_LESSONS: tuple[Lesson, ...] = (
    Lesson(
        id="ilk-proje",
        baslik="İlk proje",
        ozet="Boş bir klasörden gerçek bir projeye ilk adımı at.",
        adimlar=(
            LessonStep(
                id="proje-sec",
                baslik="Çalışma klasörünü tanı",
                aciklama=(
                    "Proje sekmesini aç; Fusion'ın hangi klasörde çalıştığını ve içindekileri gör."
                ),
                eylem=_sekme("proje"),
            ),
            LessonStep(
                id="ilk-gorev",
                baslik="İlk görevini ver",
                aciklama=(
                    "Composer'a hazır bir görev metni konur; sen göndermeden hiçbir dosya değişmez."
                ),
                eylem=_composer("Bu projede neler var, kısaca özetle."),
            ),
        ),
    ),
    Lesson(
        id="basit-oyun-veya-site",
        baslik="Basit oyun veya web sitesi",
        ozet="Tek dosyalık küçük bir oyun ya da sayfa üret ve sonucu izle.",
        adimlar=(
            LessonStep(
                id="plan-iste",
                baslik="Önce planı gör",
                aciklama=(
                    "Fusion'dan küçük bir tarayıcı oyunu ya da açılış sayfası için önce plan iste."
                ),
                eylem=_composer(
                    "Tek dosyalık basit bir tarayıcı oyunu ya da açılış sayfası için "
                    "önce kısa bir plan çıkar, kodu yazmadan önce onayımı bekle."
                ),
            ),
            LessonStep(
                id="degisiklikleri-gor",
                baslik="Oluşan dosyayı gör",
                aciklama="Proje sekmesinden yeni dosyayı ve içeriğini kontrol et.",
                eylem=_sekme("proje"),
            ),
        ),
    ),
    Lesson(
        id="varlik-ekleme-onizleme",
        baslik="Asset ekleme ve önizleme",
        ozet="Bir görsel veya ikon ekle ve sonucu önizlemede gör.",
        adimlar=(
            LessonStep(
                id="asset-ekle",
                baslik="Bir görsel ekle",
                aciklama=(
                    "Sayfaya küçük bir görsel ya da ikon eklenmesini iste; onayı sen verirsin."
                ),
                eylem=_composer("index.html içine küçük bir görsel veya ikon ekle."),
            ),
            LessonStep(
                id="onizle",
                baslik="Sonucu önizle",
                aciklama=(
                    "Proje sekmesindeki önizlemeden değişikliğin nasıl göründüğünü kontrol et."
                ),
                eylem=_sekme("proje"),
            ),
        ),
    ),
    Lesson(
        id="model-ve-dusunme-duzeyi",
        baslik="Model ve düşünme düzeyi",
        ozet="Hangi modelin, hakemin ve düşünme düzeyinin kullanıldığını gör.",
        adimlar=(
            LessonStep(
                id="durumu-gor",
                baslik="Mevcut durumu gör",
                aciklama="Kontrol panelinden aktif model, hakem, adaylar ve düşünme düzeyini gör.",
                eylem=_sekme("kontrol"),
            ),
            LessonStep(
                id="model-sor",
                baslik="Değiştirme yolunu öğren",
                aciklama="Fusion'a model ve düşünme düzeyini nasıl değiştireceğini sor.",
                eylem=_composer(
                    "Model, hakem ve düşünme düzeyimi nasıl değiştirebileceğimi kısaca anlat."
                ),
            ),
        ),
    ),
    Lesson(
        id="izinler-ve-geri-alma",
        baslik="İzinler ve geri alma",
        ozet="Küçük zararsız bir değişiklik yap, sonra geri al.",
        adimlar=(
            LessonStep(
                id="onay-modu",
                baslik="Onay modunu tanı",
                aciklama="Kontrol panelinden mevcut izin/onay modunu gör.",
                eylem=_sekme("kontrol"),
            ),
            LessonStep(
                id="degisiklik-yap",
                baslik="Küçük bir değişiklik yap",
                aciklama="Zararsız, geri alınabilir küçük bir dosya değişikliği iste.",
                eylem=_composer("Proje klasörüne test.txt adında zararsız, boş bir dosya ekle."),
            ),
            LessonStep(
                id="geri-al",
                baslik="Değişikliği geri al",
                aciklama="Proje sekmesindeki değişiklikler listesinden son adımı geri al.",
                eylem=_sekme("proje"),
            ),
        ),
    ),
    Lesson(
        id="gecmis-surdurme",
        baslik="Geçmiş sürdürme",
        ozet="Önceki bir oturumu bul ve kaldığın yerden devam et.",
        adimlar=(
            LessonStep(
                id="gecmisi-gor",
                baslik="Geçmiş oturumları gör",
                aciklama="Geçmiş sekmesinden Claude/Codex/Fusion oturumlarının listesini gör.",
                eylem=_sekme("gecmis"),
            ),
            LessonStep(
                id="surdur-iste",
                baslik="Sürdürmeyi dene",
                aciklama="Bir önceki oturumu sürdürüp kaldığın yerden devam edip edemediğini gör.",
                eylem=_composer("En son oturumumuzda nerede kaldığımızı hatırlat."),
            ),
        ),
    ),
    Lesson(
        id="beceri-ve-ajan-kullanma",
        baslik="Beceri ve ajan kullanma",
        ozet="Katalogdaki bir beceriyi veya ajanı gör ve dene.",
        adimlar=(
            LessonStep(
                id="katalogu-gor",
                baslik="Katalogu incele",
                aciklama="Yetenek sekmesinden mevcut beceri, ajan ve MCP sunucularını gör.",
                eylem=_sekme("yetenek"),
            ),
            LessonStep(
                id="beceri-dene",
                baslik="Bir beceriyi dene",
                aciklama="Katalogdaki bir beceriyi kullanan küçük bir görev ver.",
                eylem=_composer(
                    "Katalogdaki uygun bir beceriyi kullanarak bu projeyi kısaca değerlendir."
                ),
            ),
        ),
    ),
    Lesson(
        id="test-paketleme-paylasma",
        baslik="Test etme, paketleme ve paylaşma",
        ozet="Testleri çalıştır, paketleme adımlarını öğren ve paylaşmaya hazırlan.",
        adimlar=(
            LessonStep(
                id="test-calistir",
                baslik="Testleri çalıştır",
                aciklama="Süreç sekmesinden projenin test komutunu çalıştırıp sonucu izle.",
                eylem=_sekme("surec"),
            ),
            LessonStep(
                id="paketleme-sor",
                baslik="Paketleme adımlarını öğren",
                aciklama=(
                    "Fusion'a projeyi nasıl paketleyip paylaşabileceğini sor; hiçbir "
                    "adımı onaysız çalıştırma."
                ),
                eylem=_composer(
                    "Bu projeyi nasıl paketleyip arkadaşlarımla paylaşabileceğimi adım adım "
                    "anlat, ben onaylamadan hiçbirini çalıştırma."
                ),
            ),
        ),
    ),
)


def list_lessons() -> dict[str, Any]:
    """`ders.listele`: sekiz dersin kimlik/başlık/özet/adım sayısını döndür."""
    return {"ok": True, "dersler": [lesson.to_summary() for lesson in BUILTIN_LESSONS]}


def get_lesson(lesson_id: str) -> dict[str, Any]:
    """`ders.getir`: tek dersin adımlarını döndür; bilinmeyen kimlik çökmez."""
    lesson = next((item for item in BUILTIN_LESSONS if item.id == lesson_id), None)
    if lesson is None:
        return {"ok": False, "metin": f"Ders bulunamadı: {lesson_id}"}
    return lesson.to_detail()
