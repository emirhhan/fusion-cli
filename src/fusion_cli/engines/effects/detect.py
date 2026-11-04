"""Kullanıcı metninden gerçek etki sözleşmesini deterministik biçimde çıkar."""

from __future__ import annotations

import re

from ...core.text_fold import lower_tr_aware
from .model import CONTRACTS, EffectContract, EffectKind

_EXPLICIT_NO_TOOL_MARKERS = (
    "araç kullanma",
    "arac kullanma",
    "tool kullanma",
    "araç çağırma",
    "arac cagirma",
)

#: Yalnız olumsuz emir olan sözcükler: cümlecikte nerede geçerse geçsin olumsuzlama sayılır.
_NEGATED_ACTION_WORDS = (
    "kullanma",
    "çalıştırma",
    "calistirma",
    "yapma",
    "etme",
    "istemiyorum",
)
#: Hem olumsuz emir hem İSİM olan sözcükler ("arama kutusu", "yükleme ekranı", "araştırma
#: sayfası"). Bunlar yalnız cümleciğin SONUNDA (fiil kipi: "dosyayı silme", "oluşturma lütfen")
#: olumsuzlama sayılır; ardından isim geliyorsa görev olumlu kalır ve mutasyon kanıt kapısı
#: kurulur (E1-07). Ölçüldü (29 Ekim): "Arama kutusu ekle" eskiden tamamen atılıyordu.
_AMBIGUOUS_NEGATED_WORDS = (
    "oluşturma",
    "olusturma",
    "değiştirme",
    "degistirme",
    "silme",
    "gönderme",
    "gonderme",
    "yükleme",
    "yukleme",
    "arama",
    "araştırma",
    "arastirma",
)
_CLAUSE_FINAL_POLITE = r"(?:\s+(?:lütfen|lutfen|sakın|sakin|asla))?\s*$"
#: Cümle sınırı. Nokta YALNIZCA boşluk ya da satır sonu geliyorsa sınır sayılır.
#
# Ölçüldü: eski desen her noktayı bölüyordu ve `app/page.tsx` → "app/page tsx"
# oluyordu. Dosya adı bozulunca dosya-değişikliği tespiti eşleşemiyor, görev
# `workspace_read` sanılıyor ve beş araç turluk keşif bütçesine düşüyordu — oysa
# istek açıkça "span ekle, edit_file kullan" diyordu. Dosya adı geçen hemen her
# gerçek görev bu yoldan geçiyor.
_ACTION_CLAUSE_SPLIT = re.compile(
    r"(?:[.!?;](?=\s|$)|[!?;,\n]+"
    r"|\b(?:ama|fakat|ancak|lakin|ve|veya|ardından|ardindan|sonra|but|however)\b)",
    re.IGNORECASE,
)

_EN_NEGATED_MUTATION = re.compile(
    r"\b(?:do\s+not|don't|never)\s+(?:implement|repair|fix|create|modify|update|add|write)\b",
    re.IGNORECASE,
)

_EXPLANATION_MARKERS = (
    " nedir",
    " ne demek",
    " nasıl yapılır",
    " nasil yapilir",
    " nasıl çalışır",
    " nasil calisir",
    " açıkla",
    " acikla",
    " örnek ver",
    " ornek ver",
)

# Yalın "push" isim de olabilir ("web push bildirimi", "pushState", "repoya web push
# özelliği ekle"); git_push modeli hiç çağırmadan commit+push akışını başlattığı için
# yalnız FİİL biçimleri sayılır — depo/GitHub bağlamında da.
_PUSH_VERB = (
    r"(?<!web\s)\bpush(?:['’]?(?:la|le)[a-zçğıöşü]*"
    r"|\s+(?:et|yap|at)(?:ar|er|in|iniz|mek|meni|meyi|ı|i|sana|sene)?)\b"
)
_GIT_PUSH_PATTERNS = (
    r"\bgit\s+push\b",
    _PUSH_VERB,
    (
        r"(?<!web\s)\bpush\s+(?:the\s+|my\s+|your\s+|this\s+|these\s+|all\s+)?"
        r"(?:changes?|commits?|branch|code|repo|it|to)\b"
    ),
    (
        r"\b(?:github|gitlab|bitbucket)[’'a-z]*.{0,80}\b"
        r"(?:yükle|yukle|güncelle|guncelle)[a-zçğıöşü]*\b"
    ),
    (
        r"\b(?:repo|repository|depo)[a-zçğıöşü]*.{0,70}\b"
        r"(?:güncelle|guncelle|yükle|yukle)[a-zçğıöşü]*\b"
    ),
)
_GIT_COMMIT_PATTERNS = (
    r"\bgit\s+commit\b",
    # Yalnız "commit" ve emir kipi ("commit'le", "commitleyin"). Ölçüldü (30 Ekim): önceki
    # `commit(?:le)?[a-z…]*` "commitment", "committee" ve "son commitleri göster" (okuma)
    # ile de tutuyordu (E1-44).
    r"\bcommit(?:['’]?le(?:yin|yelim|yip|sene|)|)\b",
    r"\bcommit\s+(?:et|yap|oluştur|olustur)\b",
)
_SHELL_ACTION_PATTERNS = (
    (
        r"\b(?:kur|install|yükle|yukle|çalıştır|calistir|başlat|baslat|"
        r"restart|yeniden başlat|yeniden baslat|deploy|build et)\b"
    ),
    (
        # Süreç/uygulama SONLANDIRMA. `kapat` ve `sonlandır` eskiden hiçbir desende
        # yoktu: "arkadaki uygulamayı kapat" gerçek bir sistem eylemi istediği hâlde
        # sohbet sayılıyordu ve model "kapattım" dese kanıt aranmıyordu.
        r"\b(?:uygulama|program|servis|sunucu|server|süreç|surec|process|işlem|islem)"
        r"[a-zçğıöşü]*.{0,40}\b(?:kapat|durdur|sonlandır|sonlandir|öldür|oldur|kill)\b"
    ),
    (
        r"\b(?:komut|script|servis|sunucu|server|uygulama)[a-zçğıöşü]*.{0,40}\b"
        r"(?:çalıştır|calistir|başlat|baslat|durdur|yeniden başlat|restart)\b"
    ),
    # "arkada/arka planda çalışan X'i kapat" — nesne uygulama adı olabilir, tür adı
    # geçmeyebilir. Arka plan ifadesi başlı başına sistem eylemi işaretidir.
    (
        r"\b(?:arka\s*plan|arkaplan|arkada|background)[a-zçğıöşü]*.{0,60}\b"
        r"(?:kapat|durdur|sonlandır|sonlandir|öldür|oldur|kill)\b"
    ),
)
#: Uzantılı dosya adı. Kullanıcı "dosya" kelimesini YAZMAZ; doğrudan adı yazar
#: ("index.html oluştur", "app.py düzenle"). Ölçüldü: bu boşluk yüzünden model
#: hiç araç çağırmadan "dosyayı oluşturdum" diyebiliyor ve kanıt kapısı hiç
#: kurulmadığı için tur BAŞARILI sayılıyordu.
#
# Dosya adındaki nokta cümle sınırı değildir; geçmişte normalize edilmiş
# "index html" biçimiyle de uyumlu kalmak için nokta veya boşluk kabul edilir.
_FILENAME = (
    r"\b[\w/-]+[\s.](?:py|js|mjs|ts|tsx|jsx|html?|css|scss|json|ya?ml|md|txt|toml|ini|cfg|"
    r"sh|sql|go|rs|java|kt|rb|php|swift|c|cc|cpp|h|hpp)\b"
)
#: "adını yaz" / "ismini yaz" gibi CEVAP BİÇİMİ yönergeleri dosya değişikliği
#: değildir: kullanıcı metinde bir BİLGİ istiyordur, cümlede bir mutasyon nesnesi
#: (`kod`, `proje`…) geçse bile.
#
# Ölçüldü (18 Eylül, `/plan-yurut` duraklamasından sonraki tur): "Projenin kod
# adı neydi? Yalnız kod adını yaz." turu `kod` nesnesi + `yaz` fiili yüzünden
# workspace_mutation sayıldı — ikisi arasında 50 karaktere kadar herhangi bir
# metne izin veren `_FILE_MUTATION_PATTERNS` deseni `kod`u `yaz`ın nesnesi
# sandı, oysa gerçek nesne `adını`ydı. Kanıt kapısı gerçek bir dosya değişikliği
# istedi ve model soruyu cevaplamak yerine ilgisiz bir dosyayı düzenleyip
# "kanıt" üretmeye çalıştı. Bu, `_MUTATION_OBJECTS`'ten "cevap" kelimesinin
# dışarıda bırakılmasıyla aynı gerekçeye dayanır (bkz. `_matches` çağrılarından
# önceki temizlik): yalnızca `yaz`ın DOĞRUDAN nesnesi bir isim/cevap kalıbıysa
# temizlenir; "kodunu yaz" gibi gerçek mutasyonlar etkilenmez.
_ANSWER_FORMAT_PATTERN = re.compile(
    r"\b(?:ad[ıi]n[ıi]|ad[ıi]|isim|ismi|ismini)\s+(?:yaz|söyle|soyle)\b",
    re.IGNORECASE,
)
#: Dosya/proje üreten ya da değiştiren fiiller.
_MUTATION_VERBS = (
    r"(?:sil|kaldır|kaldir|taşı|tasi|kopyala|yeniden adlandır|yeniden adlandir|"
    r"değiştir|degistir|düzenle|duzenle|güncelle|guncelle|oluştur|olustur|ekle|yaz|"
    r"yap|kur|hazırla|hazirla|dönüştür|donustur)"
)
# A mutation-looking word immediately naming a pressed UI control is a label,
# not a filesystem predicate. Independent mutations remain in the request.
_UI_CONTROL_LABEL_VERB = re.compile(
    rf"\b{_MUTATION_VERBS}\b(?=\s+(?:düğme|dugme|buton|button)[a-zçğıöşü]*"
    r"\s+(?:bas|tıkla|tikla|press|click)\b)",
    re.IGNORECASE,
)

#: Kod üretimi istendiği ANLAŞILAN nesneler. "dosya" demeyen ama dosya yazdıran
#: istekler ("spor sitesi yap", "açılış sayfası hazırla") buradan yakalanır.
# Ölçüldü: "rozetin yanına ... bir span ekle" isteği hiçbir nesneye uymuyordu ve
# görev `workspace_read` sanılıp beş turluk keşif bütçesine düşüyordu — oysa
# istek açıkça bir öğe EKLEMEYİ söylüyor. Arayüz öğeleri ve metin parçaları da
# dosya değiştirir.
_MUTATION_OBJECTS = (
    r"(?:dosya|klasör|klasor|dizin|kod|proje|site|websit[a-zçğıöşü]*|sayfa|"
    r"uygulama|arayüz|arayuz|bileşen|bilesen|fonksiyon|modül|modul|test|script|betik|"
    r"metin|satır|satir|alan|buton|span|div|eleman|element|etiket|rozet|başlık|baslik|"
    r"import|bağımlılık|bagimlilik|ayar|seçenek|secenek|kural|komut)"
)

#: Türkçe rica biçimleri: "yapmanı istiyorum", "yapmasını", "yapar mısın",
#: "yapabilir misin". Ölçüldü (2 Ekim): "wordpress tabanlı bir website yapmanı
#: istiyorum ..." emir kipi olmadığı için etki tanınmadı, görev "basit" sayıldı ve
#: öğretmene plan sorulmadı.
_REQUEST_SUFFIX = (
    r"(?:man[ıi]|mas[ıi]n[ıi]|ar m[ıi]s[ıi]n|ir m[ıi]s[ıi]n|[ıi]r m[ıi]s[ıi]n|"
    r"abilir misin|ebilir misin)"
)

_FILE_MUTATION_PATTERNS = (
    rf"\b{_MUTATION_OBJECTS}[a-zçğıöşü]*.{{0,50}}\b{_MUTATION_VERBS}\b",
    rf"\b{_MUTATION_OBJECTS}[a-zçğıöşü]*.{{0,50}}\b{_MUTATION_VERBS}{_REQUEST_SUFFIX}\b",
    # Dosya adı fiilden ÖNCE ya da SONRA gelebilir: "index.html yaz" / "yaz index.html".
    rf"{_FILENAME}.{{0,40}}\b{_MUTATION_VERBS}\b",
    rf"\b{_MUTATION_VERBS}\b.{{0,40}}{_FILENAME}",
    r"\b(?:sil|kaldır|kaldir|taşı|tasi|kopyala|yeniden adlandır|yeniden adlandir)\b",
    # Kullanıcı DEĞİŞTİRİCİ ARACI adıyla söylediyse tartışma biter. "hedefli
    # edit_file kullan" cümlesi bir okuma isteği değildir.
    r"\b(?:edit_file|write_file|multi_edit)\b",
    # NESNESİZ ama tartışmasız değiştirici fiiller.
    #
    # Ölçüldü: "Ustune binmenin sebebini tespit et ve duzelt" cümlesinde fiilin
    # yanında hiçbir nesne yok (nesne iki cümle önce). Görev `workspace_read`
    # sanıldı, sekiz model çağrılık sohbet bütçesine düştü ve iş tam ilerlerken
    # "model çağrısı sınırına ulaşıldı (8)" ile kesildi.
    #
    # Liste DAR tutulur: "yaz" ve "yap" gibi çok anlamlı fiiller dışarıdadır
    # ("cevap yaz" bir dosya değişikliği değildir); buradakiler emir kipinde
    # yalnızca "bir şeyi değiştir" demektir.
    # Ek YALNIZ emir/rica kipi olabilir ("düzeltin", "ekleyelim", "silsene"). Ölçüldü
    # (30 Ekim): `[a-zçğıöşü]*` her eki kabul ediyordu; "son güncellemeleri listele",
    # "ekleme tarihini göster" gibi SALT OKUMA istekleri mutasyon sayılıp model gereksiz
    # yazma kanıtı üretmeye zorlanıyordu (E1-44).
    (
        r"\b(?:düzelt|duzelt|güncelle|guncelle|değiştir|degistir|"
        r"sil|kaldır|kaldir|oluştur|olustur|ekle)"
        r"(?:in|iniz|ın|ınız|un|unuz|ün|ünüz|yin|yiniz|yın|yınız|elim|alım|alim|yelim|yalım|yalim|"
        r"sene|sana|sin|sın|sun|sün|ip|ıp|up|üp|yip|yıp|"
        # Rica ("düzeltir misin") ve 2. tekil geçmiş ("sildin, geri al"): geçmiş SORULARI
        # `is_history_question` ayrıca eler.
        r"[ıiuü]r\s+m[ıiuü]s[ıiuü]n|[dt][ıiuü]n)?\b"
    ),
    # Geliştirme emirleri. Ölçüldü (29 Eylül): "projesini tam anlamıyla geliştir ...
    # her şeyi oku ... ayarla" görevi yalnız "proje ... oku" kalıbına uydu ve salt
    # okuma sayıldı; yazma araçları kapandı, model dört koşuda tek dosya yazamadı.
    # Kalıplar EMİR biçimleriyle sınırlıdır: "uygulama" (isim) ve "ayarlar" (isim)
    # eşleşmez.
    (
        r"\b(?:geliştir|gelistir|iyileştir|iyilestir)(?:in|elim|ir misin|ir mısın)?\b|"
        r"\b(?:uygula|ayarla)(?:yın|yin|yalım|yalim)?\b"
    ),
    # İstek bildiren kalıp: "<nesne> ... istiyorum / olsun". "bir fonksiyon daha
    # istiyorum", "Apple benzeri bir UI'a sahip olsun istiyorum" bir şeyin
    # yapılmasını ister; nesne listesi dosya üreten şeylerle sınırlıdır.
    (
        rf"\b(?:{_MUTATION_OBJECTS}|ui|özellik|ozellik|sistem|tasarım|tasarim|"
        r"sunucu|entegrasyon)[a-zçğıöşü]*\b.{0,60}\b(?:istiyorum|isterim)\b"
    ),
    # "Çalışır hale getir" ailesi: var olanı işler duruma sokmak dosya değiştirmeyi
    # gerektirir. Bu kalıp nesne-fiil desenlerine sığmıyordu (araya sıfat girer,
    # fiil ek alır) ve etki hiç kurulmadığı için model kanıtsız "yaptım" diyebiliyordu.
    (
        r"\b(?:"
        r"(?:çalışır|calisir|düzgün|duzgun|aktif|işler|isler)\s+(?:\w+\s+)?hale\s+getir|"
        r"hale\s+getir|ayağa\s+kaldır|ayaga\s+kaldir|devreye\s+al|"
        r"hayata\s+geçir|hayata\s+gecir|entegre\s+et"
        r")[a-zçğıöşü]*"
    ),
)

# İngilizce kod görevleri de aynı kanıt kapısına girmeli. ORNEK PROJE uzun
# koşusundaki "Implement a coherent stock import flow" hiçbir Türkçe fiile
# uymadığı için mutasyon gereksinimi kurulmamış, ajan salt keşifte oyalanmıştı.
_EN_FILE_MUTATION_PATTERNS = (
    r"\b(?:implement|repair|fix|create|modify|update|add)\b.{0,80}"
    r"\b(?:module|route|service|test|file|integration|feature|flow|bug|code|"
    r"website|app|import|authorization|authentication|access control|"
    r"security guard|permission check)\b",
    r"\bwrite\b.{0,40}\b(?:file|module|test|code|route)\b",
)
#: `required_effect_for`'un mutasyon/etki KÜMESİNE (`EffectKind`) ait olmayan tek
#: dize sabiti. 17 Eylül denetiminde ölçüldü: 74 bin karakterlik bir ürün
#: dökümünde "Motoplus tedarikçili, sayımı 0 olan kaç ürün var?" sorusuna model
#: metni gözüyle tarayıp "5" dedi; doğrusu 3'tü ve tedarikçisi farklı iki ürünü
#: de listeye katmıştı. Çırağın elinde zaten `run_shell` (`grep -c`, `wc -l`) ve
#: `search_code` var — eksik olan kanıt zorunluluğuydu. `EffectKind`e EKLENMEZ:
#: bu bir workflow sözleşmesi (`CONTRACTS`) değil, yalnızca kanıt kapısını
#: (`requires_tool_evidence`) tetikleyen bir etiket; `detect_contract` bilinmeyen
#: etki adında `None` döner ve normal agent akışı bozulmadan devam eder.
_BULK_COUNT_EFFECT = "bulk_count"
#: Sayma sorusunun geçtiği ölçülebilir nesne kelimeleri. Liste DAR tutulur:
#: "kaç yaşındasın", "kaç para eder", "saat kaç" gibi sıradan sohbet soruları
#: buradaki kelimelerin hiçbirini taşımadığı için eşleşmez.
_COUNTABLE_NOUNS = (
    r"(?:tane|adet|ürün|urun|dosya|kayıt|kayit|satır|satir|eşleşme|eslesme|"
    r"sonuç|sonuc|madde|kelime|karakter|öğe|oge|eleman|sipariş|siparis)"
)
_BULK_COUNT_PATTERNS = (
    # "kaç <ölçülebilir nesne> var" — miktar sorusu. Ölçüldü: gerçek denetim
    # örneği tam olarak bu kalıptaydı ("... kaç ürün var?") ve `dosya`/`listele`
    # gibi başka bir tetikleyici kelime YOKTU; bu yüzden önceki desenlerin
    # hiçbiri (`_WORKSPACE_READ_PATTERNS` dahil) eşleşmiyordu.
    rf"\bkaç\s+{_COUNTABLE_NOUNS}[a-zçğıöşü]*\b[^.!?\n]{{0,60}}\bvar\b",
    # Doğrudan sayma emri: "sayısını çıkar/bul/ver".
    r"\b(?:sayısını|sayisini|adedini)\s+(?:say|bul|çıkar|cikar|ver)[a-zçğıöşü]*\b",
    # "filtrele" ile sayma/listeleme bağlamı bir arada geçiyorsa (iki yönde de).
    r"\bfiltrele[a-zçğıöşü]*\b[^.!?\n]{0,60}\b(?:kaç|say|listele)[a-zçğıöşü]*\b",
    r"\b(?:kaç|say)[a-zçğıöşü]*\b[^.!?\n]{0,60}\bfiltrele[a-zçğıöşü]*\b",
)
_WEB_LOOKUP_PATTERNS = (
    r"\b(?:web|internet|online)[’'a-z]*.{0,25}\b(?:ara|araştır|arastir|bul|kontrol et)\b",
    r"\b(?:güncel|guncel|son durum|latest).{0,30}\b(?:ara|araştır|arastir|bul|kontrol et)\b",
)
_WORKSPACE_READ_PATTERNS = (
    (
        r"\b(?:dosya|klasör|klasor|dizin|repo|repository|proje|kod)"
        r"[a-zçğıöşü]*.{0,40}\b(?:listele|incele|kontrol et|doğrula|"
        r"dogrula|oku|ara|bul|göster|goster)\b"
    ),
    r"\b(?:git status|git diff|git log)\b",
)

#: Ajanın GEÇMİŞ işi hakkında soru: "neyi sildin?", "silmiş olabilir misin?",
#: "hangi dosyaları değiştirdin", "ne yaptın". Bunlar iş emri DEĞİLDİR.
#
# Ölçüldü (1 Ekim olayı): "hatalı bir şey silmiş olabilir misin?" içindeki "sil"
# kökü yüzünden dosya değiştirme isteği sayıldı; öğretmen kurtarma planı verdi ve
# ajan cevap yerine 11 dosyayı yeniden yazıp "tamamlandı ve doğrulandı" dedi.
_PAST_SECOND_PERSON = r"\b[a-zçğıöşü]{2,}(?:d|t)(?:ı|i|u|ü)n(?:ız|iz|uz|üz)?\b"  # sildin, yaptınız
_EVIDENTIAL_QUESTION = r"\b[a-zçğıöşü]{2,}m(?:ı|i|u|ü)ş\s+(?:olabilir\s+)?m(?:ı|i|u|ü)"
_QUESTION_SIGNAL = (
    r"\?|\bm(?:ı|i|u|ü)(?:s(?:ın|in|un|ün)(?:ız|iz|uz|üz)?)?\b|"
    r"\b(?:ne|neyi|neleri|hangi|hangisini|nereye|nerede|neden|niye|nasıl|kaç)\b"
)
#: Cümlede emir varsa geçmiş zaman sorusu sayılmaz: "sildin, geri al".
_IMPERATIVE = (
    r"\b(?:geri al|düzelt|duzelt|sil|yap|ekle|kur|oluştur|olustur|yaz|değiştir|degistir|"
    r"kaldır|kaldir|taşı|tasi|güncelle|guncelle|devam et|başlat|baslat|çalıştır|calistir|"
    r"uygula|getir|indir|yükle|yukle|gönder|gonder)\b(?!\s*m[ıiuü])"
)


def is_history_question(text: str) -> bool:
    """Mesaj ajanın geçmiş işini SORUYOR mu (iş istemiyor mu)?"""
    lowered = " ".join(lower_tr_aware(text).split())
    past = re.search(_PAST_SECOND_PERSON, lowered) or re.search(_EVIDENTIAL_QUESTION, lowered)
    if past is None or re.search(_QUESTION_SIGNAL, lowered) is None:
        return False
    return re.search(_IMPERATIVE, lowered) is None


_REPO_REFERENCE = re.compile(
    r"(?<![\w.-])(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?(?=$|[\s,;:)'\"])",
    re.IGNORECASE,
)

_BRANCH_STOPWORDS = {
    "ve",
    "ile",
    "sonra",
    "ardından",
    "ardindan",
    "önce",
    "once",
    "remote",
    "adres",
    "adresini",
    "adreslerini",
    "kontrol",
    "et",
    "push",
    "pushla",
    "pushlamak",
    "repo",
    "repository",
    "depo",
    "aktif",
    "mevcut",
    "uzak",
    "hedef",
    "olan",
    "olarak",
    "için",
    "icin",
}
_BRANCH_TOKEN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._/-]{0,126}[A-Za-z0-9])?$")


def is_valid_branch_reference(branch: str) -> bool:
    """Metinden çıkan aday gerçekten branch adı olabilir mi?

    Türkçe bağlaçları ve eylem kelimelerini branch sanmak yeni uzak dallar oluşturur;
    bu kontrol her branch çıkarımının ortak güvenlik kapısıdır.
    """

    candidate = branch.strip(" .,:;\"'")
    lowered = candidate.casefold()
    if not candidate or lowered in _BRANCH_STOPWORDS:
        return False
    if candidate.startswith(("-", "/", ".")) or candidate.endswith(("/", ".")):
        return False
    if ".." in candidate or "//" in candidate or "@{" in candidate:
        return False
    return bool(_BRANCH_TOKEN.fullmatch(candidate))


_BRANCH_PATTERNS = (
    re.compile(r"\b(?P<branch>[A-Za-z0-9._/-]+)\s+branch(?:'ine|ine|e|ı|i)?\b", re.IGNORECASE),
    re.compile(r"\bbranch(?:'ine|ine|e|ı|i)?\s+(?P<branch>[A-Za-z0-9._/-]+)", re.IGNORECASE),
    re.compile(r"\b(?:dal|branş)(?:ına|ine|a|e)?\s+(?P<branch>[A-Za-z0-9._/-]+)", re.IGNORECASE),
)


def explicitly_disallows_tools(task: str) -> bool:
    lowered = lower_tr_aware(task)
    return any(marker in lowered for marker in _EXPLICIT_NO_TOOL_MARKERS)


def required_effect_for(task: str, kind: object | None = None) -> str | None:
    """İstek gerçek bir araç etkisi istiyorsa kararlı effect kimliğini döndür."""

    del kind  # Eski çağrı imzasıyla uyumluluk; karar tamamen metinden çıkarılır.
    # Preserve sentence/newline/conjunction boundaries for object→verb binding.
    # External-effect priority still consumes the complete positive request.
    clauses = tuple(
        _ANSWER_FORMAT_PATTERN.sub(" ", clause)
        for clause in _positive_action_parts(_UI_CONTROL_LABEL_VERB.sub("", lower_tr_aware(task)))
    )
    lowered = " ".join(clauses)
    if not lowered:
        return None
    if any(marker in f" {lowered}" for marker in _EXPLANATION_MARKERS):
        return None
    if is_history_question(lowered):
        return EffectKind.WORKSPACE_READ.value
    if _matches(lowered, _GIT_PUSH_PATTERNS):
        return EffectKind.GIT_PUSH.value
    if _matches(lowered, _GIT_COMMIT_PATTERNS):
        return EffectKind.GIT_COMMIT.value
    if _matches(lowered, _SHELL_ACTION_PATTERNS):
        return EffectKind.SHELL_ACTION.value
    if any(_matches(clause, _FILE_MUTATION_PATTERNS) for clause in clauses):
        return EffectKind.WORKSPACE_MUTATION.value
    if not re.match(
        r"^(?:how\b|what\b|why\b|when\b|where\b|should i\b|can i\b|"
        r"could i\b|would i\b|is it\b|do you think\b|explain\b|describe\b|"
        r"tell me how\b)",
        lowered,
    ) and any(_matches(clause, _EN_FILE_MUTATION_PATTERNS) for clause in clauses):
        return EffectKind.WORKSPACE_MUTATION.value
    if _matches(lowered, _BULK_COUNT_PATTERNS):
        return _BULK_COUNT_EFFECT
    if _matches(lowered, _WEB_LOOKUP_PATTERNS):
        return EffectKind.WEB_LOOKUP.value
    if _matches(lowered, _WORKSPACE_READ_PATTERNS):
        return EffectKind.WORKSPACE_READ.value
    return None


def detect_contract(task: str) -> EffectContract | None:
    effect = required_effect_for(task)
    if effect is None:
        return None
    try:
        return CONTRACTS[EffectKind(effect)]
    except (ValueError, KeyError):
        return None


#: ``owner/repo`` sanılmaması gereken dizin adları: ``src/main.py``, ``app/page.tsx``.
_PATH_DIRECTORIES = frozenset(
    {
        "src", "app", "apps", "lib", "libs", "docs", "doc", "test", "tests", "public",
        "assets", "static", "scripts", "bin", "config", "components", "pages", "packages",
        "tools", "utils", "styles", "templates", "dist", "build", "node_modules", "vendor",
        "internal", "cmd", "pkg", "include", "resources", "source",
    }
)  # fmt: skip
#: Dosya uzantıları; ``repo`` bunlardan biriyle bitiyorsa referans bir DOSYA yoludur.
#: ``js`` bilerek yok: ``vercel/next.js`` gibi gerçek depo adları vardır.
_FILE_EXTENSIONS = frozenset(
    {
        "py", "ts", "tsx", "jsx", "json", "md", "txt", "html", "htm", "css", "scss", "yml",
        "yaml", "toml", "sh", "go", "rs", "java", "php", "rb", "swift", "kt", "sql", "lock",
        "cfg", "ini", "vue", "svelte", "gd", "tscn", "png", "jpg", "jpeg", "svg", "gif",
        "webp", "pdf", "csv", "xml", "log", "env", "c", "h", "cpp", "cs",
    }
)  # fmt: skip


def _looks_like_file_path(owner: str, repo: str) -> bool:
    """``src/main.py`` / ``app/page.tsx`` gibi referans depo değil dosya yolu mu?"""
    if owner.casefold() in _PATH_DIRECTORIES:
        return True
    _, ayrac, uzanti = repo.rpartition(".")
    return bool(ayrac) and uzanti.casefold() in _FILE_EXTENSIONS


def extract_repository_reference(task: str) -> str | None:
    """Metindeki ``owner/repo`` referansını çıkar; dosya yollarını yakalamamaya çalış.

    Ölçüldü (30 Ekim): son eşleşme alınıyordu ve ``app/page.tsx`` ya da ``src/main.py`` gibi
    dosya yolları depo sanılıyordu; push isteği dosya yolu geçirince sahte "Repo adı uyuşmuyor"
    sorusu çıkıyor, ``ISTEK`` cevabı origin'i ``https://github.com/src/main.py.git`` yapıyordu
    (E1-41).
    """

    matches = [
        eslesme
        for eslesme in _REPO_REFERENCE.finditer(task)
        if not _looks_like_file_path(eslesme.group("owner"), eslesme.group("repo"))
    ]
    if not matches:
        return None
    # GitHub/repo kelimesine en yakın son referans çoğunlukla hedef depodur.
    owner = matches[-1].group("owner")
    repo = matches[-1].group("repo")
    return f"{owner}/{repo}"


def extract_branch_reference(task: str) -> str | None:
    for pattern in _BRANCH_PATTERNS:
        match = pattern.search(task)
        if match:
            branch = match.group("branch").strip(" .,:;\"'")
            if is_valid_branch_reference(branch):
                return branch
    lowered = lower_tr_aware(task)
    if re.search(r"\bmain(?:\s+dal(?:ına|ine)?|\s+branch(?:'ine|ine)?)\b", lowered):
        return "main"
    if re.search(r"\bmaster(?:\s+dal(?:ına|ine)?|\s+branch(?:'ine|ine)?)\b", lowered):
        return "master"
    return None


def _is_negated_clause(clause: str) -> bool:
    lowered = lower_tr_aware(clause)
    if any(re.search(rf"\b{word}\b", lowered) for word in _NEGATED_ACTION_WORDS):
        return True
    return any(
        re.search(rf"\b{word}{_CLAUSE_FINAL_POLITE}", lowered) for word in _AMBIGUOUS_NEGATED_WORDS
    )


def _positive_action_parts(text: str) -> tuple[str, ...]:
    """Olumlu cümlecikleri koru, açık olumsuz talimatları at.

    ``repoyu pushla ama araç kullanma`` gerçek bir push isteği olarak KALIR: kullanıcı
    aracı yasaklamış olabilir ama istediği etki ortadan kalkmaz. Buna karşılık
    ``git kullanma; dosya oluştur`` yalnızca dosya cümleciğini bırakır.
    """
    positive: list[str] = []
    start = 0
    previous_separator = ""
    previous_positive = False
    for boundary in [*_ACTION_CLAUSE_SPLIT.finditer(text), None]:
        end = boundary.start() if boundary is not None else len(text)
        clause = " ".join(text[start:end].split())
        keep = (
            bool(clause)
            and not _is_negated_clause(clause)
            and not _EN_NEGATED_MUTATION.search(clause)
        )
        if keep:
            # Coordinated objects keep their shared verb ("uygulama ve oyun yap").
            # A completed predicate ("uygulamayı aç ve ... yap") cannot lend its
            # object to the next predicate. Sentence boundaries never merge.
            if (
                previous_positive
                and previous_separator in {"ve", "veya", ","}
                and _ends_with_build_object(positive[-1])
            ):
                positive[-1] = f"{positive[-1]} {clause}"
            else:
                positive.append(clause)
        previous_positive = keep
        if boundary is not None:
            previous_separator = boundary.group().strip().lower()
            start = boundary.end()
    return tuple(positive)


def _ends_with_build_object(clause: str) -> bool:
    tail = clause.rsplit(maxsplit=1)[-1]
    return bool(re.fullmatch(rf"{_MUTATION_OBJECTS}[a-zçğıöşü]*", tail)) or (
        tail.rsplit(".", 1)[-1] in _FILE_EXTENSIONS
    )


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in patterns)
