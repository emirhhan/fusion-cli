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
    """Bir dersin tek adımı: başlık, açıklama, önizleme ve tek güvenli eylem.

    `onizleme` kullanıcının DENEMEDEN ÖNCE ne olacağını görmesi içindir:
    composer eyleminde gönderilecek metnin tam hali, sekme eyleminde o sekmede
    ne göreceğinin kısa tarifi. Sürprizle karşılaşmadan ilerlemek, dersin
    öğretici olmasının koşuludur.
    """

    id: str
    baslik: str
    aciklama: str
    onizleme: str
    eylem: LessonAction

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "baslik": self.baslik,
            "aciklama": self.aciklama,
            "onizleme": self.onizleme,
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
        ozet="Fusion'ın nerede çalıştığını anla ve ilk görevini ver.",
        adimlar=(
            LessonStep(
                id="kip",
                baslik="Sohbet mi, kod mu?",
                aciklama=(
                    "Fusion iki kipte çalışır. Sohbet kipinde tek yapay zekâyla konuşursun ve "
                    "Fusion kendiliğinden dosyalarına dokunmaz. Kod kipinde bir klasöre bağlanır "
                    "ve orada iş yapar. Kipi görev kutusunun altındaki düğmeden ya da "
                    "Shift+Tab ile "
                    "değiştirirsin."
                ),
                onizleme="Görev kutusunun altında Sohbet ve Kod düğmelerini göreceksin.",
                eylem=_composer("Sohbet kipi ile kod kipi arasındaki farkı bana kısaca anlat."),
            ),
            LessonStep(
                id="klasor",
                baslik="Çalışma klasörünü seç",
                aciklama=(
                    "Kod kipinde Fusion bir klasörün içinde çalışır ve o klasörün dışına "
                    "kendiliğinden çıkamaz. Masaüstündeki boş bir klasör bile olur; deneme yapmak "
                    "için yeni bir tane açman en güvenlisidir."
                ),
                onizleme=(
                    "Yeni görev → Klasörde kod görevi, işletim sisteminin klasör seçicisini açar."
                ),
                eylem=_sekme("proje"),
            ),
            LessonStep(
                id="icerik",
                baslik="Klasörde ne var, gör",
                aciklama=(
                    "Sağdaki Dosyalar sekmesi seçtiğin klasörün gerçek içeriğini gösterir. "
                    "Bir dosyaya tıkladığında içeriğini satır numaralarıyla okursun. Fusion da "
                    "aynı sınırın içinden okur; senin görmediğin bir yere bakmaz."
                ),
                onizleme="Dosyalar sekmesinde klasörün ağacı ve seçtiğin dosyanın içeriği görünür.",
                eylem=_sekme("proje"),
            ),
            LessonStep(
                id="ilk-gorev",
                baslik="İlk görevini ver",
                aciklama=(
                    "Görev kutusuna ne istediğini normal cümlelerle yaz. Teknik terim kullanman "
                    "gerekmez. Aşağıdaki metin kutuya hazır olarak konur; göndermeye sen karar "
                    "verirsin."
                ),
                onizleme="Bu projede neler var, kısaca özetle.",
                eylem=_composer("Bu projede neler var, kısaca özetle."),
            ),
            LessonStep(
                id="olaylar",
                baslik="Ne yaptığını izle",
                aciklama=(
                    "Fusion çalışırken cevabın üstünde ne yaptığını satır satır yazar: hangi "
                    "dosyayı okudu, hangi komutu çalıştırdı, ne değişti. Bu satırlara tıklayıp "
                    "ayrıntısını açabilirsin; 'yaptım' demesiyle yetinmen gerekmez."
                ),
                onizleme="Cevabın üstünde açılıp kapanan çalışma satırlarını göreceksin.",
                eylem=_sekme("proje"),
            ),
            LessonStep(
                id="dogrula",
                baslik="Söylediğini doğrula",
                aciklama=(
                    "Bir turun sonunda Fusion yalnız o turda gerçekten değişen dosyaları listeler. "
                    "Hiçbir şey değişmediyse bunu da açıkça söyler. Alışkanlık edin: "
                    "iddiayı değil, "
                    "değişiklik listesini oku."
                ),
                onizleme="Değişiklikler sekmesinde bu turda değişen dosyalar listelenir.",
                eylem=_sekme("proje"),
            ),
        ),
    ),
    Lesson(
        id="basit-oyun-veya-site",
        baslik="Basit oyun veya web sitesi",
        ozet="Tek dosyalık küçük bir şey üret, çalıştır ve düzelt.",
        adimlar=(
            LessonStep(
                id="plan-iste",
                baslik="Önce planı iste",
                aciklama=(
                    "Doğrudan 'kodu yaz' demek yerine önce plan istemek, yanlış yöne gidilen "
                    "turları baştan keser. Fusion planı yazar, sen onaylarsan kodlamaya geçer."
                ),
                onizleme=(
                    "Tek dosyalık basit bir tarayıcı oyunu için önce kısa bir plan çıkar, "
                    "kodu yazmadan önce onayımı bekle."
                ),
                eylem=_composer(
                    "Tek dosyalık basit bir tarayıcı oyunu için önce kısa bir plan çıkar, "
                    "kodu yazmadan önce onayımı bekle."
                ),
            ),
            LessonStep(
                id="onay",
                baslik="Onay penceresini tanı",
                aciklama=(
                    "Fusion bir dosya oluşturmadan ya da değiştirmeden önce sana sorar. Üç "
                    "seçenek vardır: bir kez izin ver, bu oturum boyunca izin ver, reddet. "
                    "Reddetmek turu bitirmez; Fusion başka bir yol dener."
                ),
                onizleme="Dosya değişikliğinden önce üç seçenekli onay penceresi açılır.",
                eylem=_composer("Şimdi planı uygula ve dosyayı oluştur."),
            ),
            LessonStep(
                id="dosyayi-gor",
                baslik="Oluşan dosyayı aç",
                aciklama=(
                    "Dosyalar sekmesinden yeni dosyayı aç ve içeriğine bak. Kodun tamamını "
                    "anlaman gerekmez; hangi bölümün ne işe yaradığını Fusion'a sorabilirsin."
                ),
                onizleme="Dosyalar sekmesinde yeni oluşan dosya ve içeriği görünür.",
                eylem=_sekme("proje"),
            ),
            LessonStep(
                id="onizle",
                baslik="Sonucu önizle",
                aciklama=(
                    "Önizleme sekmesi HTML dosyasını uygulamanın içinde açar. Betikler güvenlik "
                    "için kum havuzunda çalışır; dış siteler gömülmez."
                ),
                onizleme="Önizleme sekmesinde sayfanın kendisi görünür.",
                eylem=_sekme("proje"),
            ),
            LessonStep(
                id="degistir",
                baslik="Bir şeyi değiştir",
                aciklama=(
                    "Küçük bir değişiklik iste: renk, yazı, hız. Küçük adımlarla ilerlemek, "
                    "bir şey bozulduğunda nedenini bulmayı kolaylaştırır."
                ),
                onizleme="Oyunun rengini değiştir ve neyi neden değiştirdiğini tek cümleyle söyle.",
                eylem=_composer(
                    "Oyunun rengini değiştir ve neyi neden değiştirdiğini tek cümleyle söyle."
                ),
            ),
            LessonStep(
                id="bozulursa",
                baslik="Bozulursa ne yapılır",
                aciklama=(
                    "Bir değişiklik sonucu bozarsa Değişiklikler sekmesinden o dosyayı eski "
                    "hâline döndürebilirsin. Bu, ikinci bir onay ister ve yalnız o dosyayı etkiler."
                ),
                onizleme="Değişiklikler sekmesinde her dosyanın yanında geri alma seçeneği vardır.",
                eylem=_sekme("proje"),
            ),
        ),
    ),
    Lesson(
        id="varlik-ekleme-onizleme",
        baslik="Görsel ve dosya ekleme",
        ozet="Kendi dosyanı Fusion'a ver ve sonucu önizle.",
        adimlar=(
            LessonStep(
                id="atac",
                baslik="Ataç ile dosya ekle",
                aciklama=(
                    "Görev kutusunun solundaki ataç düğmesi işletim sisteminin dosya seçicisini "
                    "açar. Birden çok dosya seçebilirsin; seçtiklerin kutunun üstünde etiket "
                    "olarak görünür ve göndermeden önce kaldırabilirsin."
                ),
                onizleme="Ataç düğmesi çoklu seçime izin veren dosya seçicisini açar.",
                eylem=_composer("Eklediğim dosyada ne olduğunu anlat."),
            ),
            LessonStep(
                id="surukle",
                baslik="Sürükleyip bırak",
                aciklama=(
                    "Dosyayı doğrudan görev kutusunun üstüne sürükleyip bırakabilirsin. Görsel "
                    "dosyalar görsel olarak, ötekiler normal dosya olarak eklenir."
                ),
                onizleme="Sürüklediğin dosya kutunun üstünde etiket olarak belirir.",
                eylem=_sekme("proje"),
            ),
            LessonStep(
                id="gorsel-iste",
                baslik="Görsel ekletmek",
                aciklama=(
                    "Sayfana bir görsel eklenmesini isteyebilirsin. Fusion görseli nereye "
                    "koyacağını ve nasıl bağlayacağını sana onaylatır."
                ),
                onizleme="Sayfaya küçük bir görsel ya da ikon ekle.",
                eylem=_composer("Sayfaya küçük bir görsel ya da ikon ekle."),
            ),
            LessonStep(
                id="onizlemede-gor",
                baslik="Önizlemede kontrol et",
                aciklama=(
                    "Önizleme sekmesi görsel, ses, video ve PDF dosyalarını uygulama içinde "
                    "gösterir. Dosya proje klasörünün dışındaysa açılmaz; bu bilinçli bir sınırdır."
                ),
                onizleme="Önizleme sekmesinde seçtiğin dosyanın kendisi görünür.",
                eylem=_sekme("proje"),
            ),
            LessonStep(
                id="boyut",
                baslik="Neden bazı dosyalar açılmaz",
                aciklama=(
                    "Önizleme 8 MB üstündeki dosyaları ve tanınmayan türleri açmaz. Sebebi "
                    "söylenir; sessizce boş bir kutu göstermez. Büyük dosyayı yine de Fusion'a "
                    "verebilirsin, yalnız önizleme yapılmaz."
                ),
                onizleme="Desteklenmeyen türde sebebi yazan kısa bir uyarı görürsün.",
                eylem=_sekme("proje"),
            ),
            LessonStep(
                id="gizlilik",
                baslik="Eklediğin dosya nereye gider",
                aciklama=(
                    "Eklediğin dosyanın yolu ve içeriği yalnız o turda seçtiğin modele gider. "
                    "Fusion dosyalarını hiçbir sunucuda saklamaz; her şey bu bilgisayarda kalır."
                ),
                onizleme="Ayarlar ekranındaki Gizlilik kartı bu davranışı özetler.",
                eylem=_sekme("kontrol"),
            ),
        ),
    ),
    Lesson(
        id="model-ve-dusunme-duzeyi",
        baslik="Model ve düşünme düzeyi",
        ozet="Hangi yapay zekânın çalıştığını gör ve değiştir.",
        adimlar=(
            LessonStep(
                id="durumu-gor",
                baslik="Şu an hangi model çalışıyor",
                aciklama=(
                    "Kontrol Paneli'ndeki Model düzeni kartı dört şeyi gösterir: ajan (asıl işi "
                    "yapan), hakem (cevapları karşılaştıran), adaylar (aynı soruyu paralel "
                    "yanıtlayanlar) ve düşünme düzeyi."
                ),
                onizleme=(
                    "Kontrol Paneli'nde ajan, hakem, adaylar ve yönlendirme satırlarını görürsün."
                ),
                eylem=_sekme("kontrol"),
            ),
            LessonStep(
                id="degistir",
                baslik="Modeli değiştir",
                aciklama=(
                    "Model düzeni kartındaki düğmeler seçim penceresini açar. Değişiklik bir "
                    "sonraki turda değil, HEMEN geçerli olur."
                ),
                onizleme="Ajan modelini değiştir düğmesi model seçicisini açar.",
                eylem=_sekme("kontrol"),
            ),
            LessonStep(
                id="duzey",
                baslik="Düşünme düzeyi ne işe yarar",
                aciklama=(
                    "Yüksek düzey daha uzun düşünür ve karmaşık işte daha iyi sonuç verir; düşük "
                    "düzey hızlıdır ve kotanı daha az harcar. Basit sorularda düşük düzey yeter."
                ),
                onizleme="Düşünme düzeyini değiştir düğmesi kademe seçicisini açar.",
                eylem=_sekme("kontrol"),
            ),
            LessonStep(
                id="web",
                baslik="Kendi aboneliğini bağla",
                aciklama=(
                    "ChatGPT, Claude, Gemini ve Copilot'a kendi aboneliğinle bağlanabilirsin. "
                    "API anahtarı gerekmez: Giriş yap düğmesi ayrı bir pencere açar, orada normal "
                    "şekilde giriş yaparsın ve oturum bu bilgisayarda kalır."
                ),
                onizleme=(
                    "Kontrol Paneli'ndeki Web sağlayıcıları kartında dört sağlayıcı listelenir."
                ),
                eylem=_sekme("kontrol"),
            ),
            LessonStep(
                id="kota",
                baslik="Kotanı koru",
                aciklama=(
                    "Ücretsiz sağlayıcıların sınırları farklı çalışır. Bir sınıra takıldığında "
                    "Fusion nedenini ve ne yapman gerektiğini söyler; sessizce durmaz."
                ),
                onizleme="Sınıra takıldığında ne yapman gerektiğini yazan bir açıklama görürsün.",
                eylem=_composer("Hangi sağlayıcıların sınırlarına takılıyorum ve ne yapmalıyım?"),
            ),
            LessonStep(
                id="sor",
                baslik="Emin değilsen sor",
                aciklama=(
                    "Hangi modelin ne için iyi olduğunu ezberlemen gerekmez. Fusion'a yapmak "
                    "istediğin işi anlat, sana uygun düzeni önersin."
                ),
                onizleme="Şu işi yapacağım: … Bunun için hangi model ve düşünme düzeyi uygun?",
                eylem=_composer(
                    "Şu işi yapacağım: bir web sitesi kuracağım. "
                    "Bunun için hangi model ve düşünme düzeyi uygun?"
                ),
            ),
        ),
    ),
    Lesson(
        id="izinler-ve-geri-alma",
        baslik="İzinler ve geri alma",
        ozet="Fusion'ın neye dokunabildiğini sen belirle.",
        adimlar=(
            LessonStep(
                id="onay-modu",
                baslik="Onay modunu tanı",
                aciklama=(
                    "Üç mod vardır: her işlemde sor, otomatik ilerle, yalnız planla. Yeni "
                    "başlıyorsan 'her işlemde sor' en güvenlisidir; ne olduğunu görerek öğrenirsin."
                ),
                onizleme="Kontrol Paneli'ndeki İzinler kartında çalışma modu yazar.",
                eylem=_sekme("kontrol"),
            ),
            LessonStep(
                id="kapsam",
                baslik="Dosya kapsamı",
                aciklama=(
                    "Fusion seçtiğin klasörün dışına kendiliğinden çıkamaz. Dışarıdaki bir "
                    "dosyaya erişmesi gerekirse sana sorar ve sen izin verirsen erişir."
                ),
                onizleme="İzinler kartında dosya kapsamı satırı bu sınırı gösterir.",
                eylem=_sekme("kontrol"),
            ),
            LessonStep(
                id="degisiklik-yap",
                baslik="Zararsız bir değişiklik yap",
                aciklama=(
                    "Denemek için geri alınabilir, küçük bir değişiklik iste. Onay penceresi "
                    "çıkınca ne yapılacağını okuyup öyle onayla."
                ),
                onizleme="Proje klasörüne test.txt adında zararsız, boş bir dosya ekle.",
                eylem=_composer("Proje klasörüne test.txt adında zararsız, boş bir dosya ekle."),
            ),
            LessonStep(
                id="degisikligi-gor",
                baslik="Ne değiştiğini gör",
                aciklama=(
                    "Değişiklikler sekmesi yalnız Fusion'ın değil, senin de yaptığın "
                    "değişiklikleri gösterir. Her satırın yanında eski ve yeni hâli vardır."
                ),
                onizleme="Değişiklikler sekmesinde eklenen ve silinen satırlar renkli görünür.",
                eylem=_sekme("proje"),
            ),
            LessonStep(
                id="geri-al",
                baslik="Geri al",
                aciklama=(
                    "Bir dosyayı eski hâline döndürmek ikinci bir onay ister ve yalnız o dosyayı "
                    "etkiler. Başka değişikliklerin kaybolmaz."
                ),
                onizleme="Geri alma, seçtiğin dosyayı önceki hâline döndürür.",
                eylem=_sekme("proje"),
            ),
            LessonStep(
                id="reddet",
                baslik="Reddetmekten çekinme",
                aciklama=(
                    "Anlamadığın bir onayı reddetmek doğru davranıştır. Fusion turu bitirmez; "
                    "ya başka bir yol dener ya da neden gerektiğini açıklar."
                ),
                onizleme="Reddettiğinde Fusion nedenini açıklayıp alternatif önerir.",
                eylem=_composer("Az önce ne yapmak istediğini ve neden gerektiğini açıkla."),
            ),
        ),
    ),
    Lesson(
        id="gecmis-surdurme",
        baslik="Geçmiş sürdürme",
        ozet="Claude ve Codex'te kaldığın yerden devam et.",
        adimlar=(
            LessonStep(
                id="kaynaklar",
                baslik="Hangi geçmişler var",
                aciklama=(
                    "Fusion bu bilgisayarda kurulu Claude, Codex ve Hermes geçmişlerini bulur. "
                    "Yalnız gerçekten kurulu olanlar kenar çubuğunda görünür; olmayan bir kaynak "
                    "hiç listelenmez."
                ),
                onizleme="Kenar çubuğunda yalnız kurulu geçmiş kaynakları listelenir.",
                eylem=_sekme("gecmis"),
            ),
            LessonStep(
                id="listele",
                baslik="Konuşmaları gör",
                aciklama=(
                    "Bir kaynağı açtığında o araçtaki konuşmalar tarih sırasıyla listelenir. "
                    "Liste sayfa sayfa yüklenir; binlerce konuşma olsa bile uygulama yavaşlamaz."
                ),
                onizleme="Seçtiğin kaynağın konuşma listesi tarih sırasıyla açılır.",
                eylem=_sekme("gecmis"),
            ),
            LessonStep(
                id="onizle",
                baslik="Devralmadan önce oku",
                aciklama=(
                    "Bir konuşmayı seçtiğinde içeriğini salt okunur olarak önizlersin. "
                    "Devralmadan önce doğru konuşma mı diye bakabilirsin."
                ),
                onizleme="Seçtiğin konuşmanın mesajları sağda önizlenir.",
                eylem=_sekme("gecmis"),
            ),
            LessonStep(
                id="sir",
                baslik="Hassas değer uyarısı",
                aciklama=(
                    "Konuşmada API anahtarı gibi hassas bir değer varsa Fusion bunu sayıyla "
                    "bildirir. Değeri göstermez ve saklamaz; yalnız haberin olsun diye söyler."
                ),
                onizleme="Hassas değer varsa önizlemenin üstünde sakin bir uyarı çıkar.",
                eylem=_sekme("gecmis"),
            ),
            LessonStep(
                id="surdur",
                baslik="Devral",
                aciklama=(
                    "Devraldığında o konuşmanın özeti YENİ bir sohbete taşınır; eski konuşma "
                    "değişmez. Devralınan bağlam yalnız bir sonraki turda kullanılır."
                ),
                onizleme="Devralma yeni bir sohbet açar ve özeti oraya taşır.",
                eylem=_sekme("gecmis"),
            ),
            LessonStep(
                id="dogrula",
                baslik="Doğru yerden devam ettiğini doğrula",
                aciklama=(
                    "Devraldıktan sonra ilk soruyu bağlamı sınayacak şekilde sor. Fusion yanlış "
                    "konuşmayı devraldıysa bunu ilk turda anlarsın."
                ),
                onizleme="En son nerede kalmıştık, kısaca özetle.",
                eylem=_composer("En son nerede kalmıştık, kısaca özetle."),
            ),
        ),
    ),
    Lesson(
        id="beceri-ve-ajan-kullanma",
        baslik="Beceri ve ajan kullanma",
        ozet="Bilgisayarındaki hazır uzmanlıkları Fusion'a bağla.",
        adimlar=(
            LessonStep(
                id="katalog",
                baslik="Katalogda ne var",
                aciklama=(
                    "Beceriler ve Ajanlar ekranı bilgisayarındaki Claude, Codex ve Fusion "
                    "becerilerini tek listede toplar. Aynı beceri iki araçta da varsa tek satırda "
                    "iki etiketle görünür."
                ),
                onizleme=(
                    "Katalogda beceriler, ajanlar, proje talimatları ve MCP sunucuları listelenir."
                ),
                eylem=_sekme("yetenek"),
            ),
            LessonStep(
                id="detay",
                baslik="Bir becerinin içine bak",
                aciklama=(
                    "Bir beceriye tıkladığında ne yaptığını ve hangi izinleri istediğini "
                    "okursun. Metni okumak, o beceriye komut ya da ağ izni vermez."
                ),
                onizleme="Seçtiğin becerinin açıklaması ve izin etiketleri görünür.",
                eylem=_sekme("yetenek"),
            ),
            LessonStep(
                id="izin",
                baslik="İzinleri anla",
                aciklama=(
                    "İzin etiketleri sade Türkçedir: dosya okuma, komut çalıştırma, dış araçlar. "
                    "Bir beceri ne isterse istesin, senin onay modun geçerlidir."
                ),
                onizleme="Her satırın yanında istediği izinler etiket olarak yazar.",
                eylem=_sekme("yetenek"),
            ),
            LessonStep(
                id="kapat",
                baslik="İstemediğini kapat",
                aciklama=(
                    "Bir beceriyi ya da ajanı bu oturum için kapatabilirsin. Kapattığın öğe "
                    "Fusion'ın gerçek listesinden çıkar; yalnız gizlenmiş olmaz."
                ),
                onizleme="Kapattığın öğe o oturumda Fusion'a hiç sunulmaz.",
                eylem=_sekme("yetenek"),
            ),
            LessonStep(
                id="kullan",
                baslik="Bir beceriyi dene",
                aciklama=(
                    "Bir beceriyi açıkça seçip sonraki turda kullanmasını isteyebilirsin. "
                    "Fusion uygun beceriyi kendiliğinden de seçer ve bunu sohbet akışında söyler."
                ),
                onizleme="Katalogdaki uygun bir beceriyi kullanarak bu projeyi kısaca değerlendir.",
                eylem=_composer(
                    "Katalogdaki uygun bir beceriyi kullanarak bu projeyi kısaca değerlendir."
                ),
            ),
            LessonStep(
                id="mcp",
                baslik="MCP sunucuları",
                aciklama=(
                    "MCP, Fusion'a dış araçlar bağlamanın standart yoludur. Kurulu sunucular "
                    "katalogda görünür ve tıpkı beceriler gibi oturumluk kapatılabilir."
                ),
                onizleme="Katalogda MCP başlığı altında kurulu sunucular listelenir.",
                eylem=_sekme("yetenek"),
            ),
        ),
    ),
    Lesson(
        id="test-paketleme-paylasma",
        baslik="Test etme, paketleme ve paylaşma",
        ozet="Yaptığın şeyi doğrula ve başkasına ver.",
        adimlar=(
            LessonStep(
                id="komutlar",
                baslik="Projenin komutlarını bul",
                aciklama=(
                    "Testler sekmesi projenin yapısına bakıp test, lint ve derleme komutlarını "
                    "kendi bulur. Komut ezberlemen gerekmez ama çalıştırmadan önce hangisinin "
                    "çalışacağını görürsün."
                ),
                onizleme="Testler sekmesinde önerilen komutlar düğme olarak listelenir.",
                eylem=_sekme("surec"),
            ),
            LessonStep(
                id="calistir",
                baslik="Testleri çalıştır",
                aciklama=(
                    "Bir komutu çalıştırdığında çıktısı canlı akar. Süreç bittiğinde çıkış kodu "
                    "yazılır; geçti mi kaldı mı tahmin etmen gerekmez."
                ),
                onizleme="Komut çıktısı satır satır akar ve sonunda çıkış kodu yazar.",
                eylem=_sekme("surec"),
            ),
            LessonStep(
                id="hata",
                baslik="Kırmızıysa ne yapılır",
                aciklama=(
                    "Test başarısızsa çıktıyı olduğu gibi Fusion'a verebilirsin. Hatanın kendisini "
                    "okumak, 'düzelt' demekten daha iyi sonuç verir."
                ),
                onizleme="Testler başarısız oldu, çıktıyı inceleyip nedenini açıkla ve düzelt.",
                eylem=_composer(
                    "Testler başarısız oldu, çıktıyı inceleyip nedenini açıkla ve düzelt."
                ),
            ),
            LessonStep(
                id="git",
                baslik="Git durumunu gör",
                aciklama=(
                    "Testler sekmesi ayrıca hangi daldasın, kaç dosya değişmiş ve uzak dala göre "
                    "ne kadar önde/gerideysen onu gösterir. Git bilmiyorsan bunu Fusion'a "
                    "sorabilirsin."
                ),
                onizleme="Dal adı, değişen dosya sayısı ve önde/geride durumu görünür.",
                eylem=_sekme("surec"),
            ),
            LessonStep(
                id="paketle",
                baslik="Paketlemeyi öğren",
                aciklama=(
                    "Yaptığın şeyi başkasına vermek için nasıl paketleyeceğini Fusion adım adım "
                    "anlatabilir. Hiçbir adımı sen onaylamadan çalıştırmaz."
                ),
                onizleme=(
                    "Bu projeyi nasıl paketleyip arkadaşlarımla paylaşabileceğimi adım adım "
                    "anlat, ben onaylamadan hiçbirini çalıştırma."
                ),
                eylem=_composer(
                    "Bu projeyi nasıl paketleyip arkadaşlarımla paylaşabileceğimi adım adım "
                    "anlat, ben onaylamadan hiçbirini çalıştırma."
                ),
            ),
            LessonStep(
                id="paylas",
                baslik="Paylaşmadan önce kontrol et",
                aciklama=(
                    "Paylaşmadan önce içinde anahtar, parola ya da kişisel veri kalmadığından "
                    "emin ol. Fusion'a dosyaları tarayıp böyle bir şey var mı diye sorabilirsin."
                ),
                onizleme=(
                    "Paylaşmadan önce projede anahtar, parola veya kişisel veri var mı kontrol et."
                ),
                eylem=_composer(
                    "Paylaşmadan önce projede anahtar, parola veya kişisel veri var mı kontrol et."
                ),
            ),
        ),
    ),
)


def list_lessons() -> dict[str, Any]:
    """`ders.listele`: sekiz dersin özeti, sabit sırayla."""
    return {"ok": True, "dersler": [lesson.to_summary() for lesson in BUILTIN_LESSONS]}


def get_lesson(lesson_id: str) -> dict[str, Any]:
    """`ders.getir`: tek dersin adımları.

    Bilinmeyen kimlik süreci ÇÖKERTMEZ; anlaşılır bir hata döner.
    """
    for lesson in BUILTIN_LESSONS:
        if lesson.id == lesson_id:
            return lesson.to_detail()
    return {"ok": False, "metin": f"Ders bulunamadı: {lesson_id}"}
