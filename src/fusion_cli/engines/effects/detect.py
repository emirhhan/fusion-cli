"""Kullanıcı metninden gerçek etki sözleşmesini deterministik biçimde çıkar."""

from __future__ import annotations

import re

from .model import CONTRACTS, EffectContract, EffectKind

_EXPLICIT_NO_TOOL_MARKERS = (
    "araç kullanma",
    "arac kullanma",
    "tool kullanma",
    "araç çağırma",
    "arac cagirma",
)

_NEGATED_ACTION_WORDS = (
    "kullanma",
    "çalıştırma",
    "calistirma",
    "yapma",
    "etme",
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
    "istemiyorum",
)
#: Cümle sınırı. Nokta YALNIZCA boşluk ya da satır sonu geliyorsa sınır sayılır.
#
# Ölçüldü: eski desen her noktayı bölüyordu ve `app/page.tsx` → "app/page tsx"
# oluyordu. Dosya adı bozulunca dosya-değişikliği tespiti eşleşemiyor, görev
# `workspace_read` sanılıyor ve beş araç turluk keşif bütçesine düşüyordu — oysa
# istek açıkça "span ekle, edit_file kullan" diyordu. Dosya adı geçen hemen her
# gerçek görev bu yoldan geçiyor.
_ACTION_CLAUSE_SPLIT = re.compile(
    r"(?:[.!?;](?=\s|$)|[!?;\n]+"
    r"|\b(?:ama|fakat|ancak|lakin|ve|veya|ardından|ardindan|sonra)\b)",
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

_GIT_PUSH_PATTERNS = (
    r"\bgit\s+push\b",
    r"\bpush(?:la|le)?[a-zçğıöşü]*\b",
    r"\bpush\s+et[a-zçğıöşü]*\b",
    (
        r"\b(?:github|gitlab|bitbucket)[’'a-z]*.{0,80}\b"
        r"(?:yükle|yukle|güncelle|guncelle|push)[a-zçğıöşü]*\b"
    ),
    (
        r"\b(?:repo|repository|depo)[a-zçğıöşü]*.{0,70}\b"
        r"(?:push|güncelle|guncelle|yükle|yukle)[a-zçğıöşü]*\b"
    ),
)
_GIT_COMMIT_PATTERNS = (
    r"\bgit\s+commit\b",
    r"\bcommit(?:le)?[a-zçğıöşü]*\b",
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
# Ayraç nokta VEYA boşluktur: `_positive_action_clauses` noktalama işaretlerini
# siliyor ve normalize edilmiş metinde "index.html" → "index html" oluyor. Yalnızca
# noktayı arayan bir desen bu yüzden HİÇ eşleşmez — ölçüldü.
_FILENAME = (
    r"\b[\w/-]+[\s.](?:py|js|mjs|ts|tsx|jsx|html?|css|scss|json|ya?ml|md|txt|toml|ini|cfg|"
    r"sh|sql|go|rs|java|kt|rb|php|swift|c|cc|cpp|h|hpp)\b"
)
#: Dosya/proje üreten ya da değiştiren fiiller.
_MUTATION_VERBS = (
    r"(?:sil|kaldır|kaldir|taşı|tasi|kopyala|yeniden adlandır|yeniden adlandir|"
    r"değiştir|degistir|düzenle|duzenle|güncelle|guncelle|oluştur|olustur|ekle|yaz|"
    r"yap|kur|hazırla|hazirla|dönüştür|donustur)"
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

_FILE_MUTATION_PATTERNS = (
    rf"\b{_MUTATION_OBJECTS}[a-zçğıöşü]*.{{0,50}}\b{_MUTATION_VERBS}\b",
    # Dosya adı fiilden ÖNCE ya da SONRA gelebilir: "index.html yaz" / "yaz index.html".
    rf"{_FILENAME}.{{0,40}}\b{_MUTATION_VERBS}\b",
    rf"\b{_MUTATION_VERBS}\b.{{0,40}}{_FILENAME}",
    r"\b(?:sil|kaldır|kaldir|taşı|tasi|kopyala|yeniden adlandır|yeniden adlandir)\b",
    # Kullanıcı DEĞİŞTİRİCİ ARACI adıyla söylediyse tartışma biter. "hedefli
    # edit_file kullan" cümlesi bir okuma isteği değildir.
    r"\b(?:edit_file|write_file|multi_edit)\b",
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
    lowered = task.lower()
    return any(marker in lowered for marker in _EXPLICIT_NO_TOOL_MARKERS)


def required_effect_for(task: str, kind: object | None = None) -> str | None:
    """İstek gerçek bir araç etkisi istiyorsa kararlı effect kimliğini döndür."""

    del kind  # Eski çağrı imzasıyla uyumluluk; karar tamamen metinden çıkarılır.
    lowered = " ".join(task.lower().split())
    lowered = _positive_action_clauses(lowered)
    if not lowered:
        return None
    if any(marker in f" {lowered}" for marker in _EXPLANATION_MARKERS):
        return None
    if _matches(lowered, _GIT_PUSH_PATTERNS):
        return EffectKind.GIT_PUSH.value
    if _matches(lowered, _GIT_COMMIT_PATTERNS):
        return EffectKind.GIT_COMMIT.value
    if _matches(lowered, _SHELL_ACTION_PATTERNS):
        return EffectKind.SHELL_ACTION.value
    if _matches(lowered, _FILE_MUTATION_PATTERNS):
        return EffectKind.WORKSPACE_MUTATION.value
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


def extract_repository_reference(task: str) -> str | None:
    """Metindeki ``owner/repo`` referansını çıkar; dosya yollarını yakalamamaya çalış."""

    matches = list(_REPO_REFERENCE.finditer(task))
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
    lowered = task.lower()
    if re.search(r"\bmain(?:\s+dal(?:ına|ine)?|\s+branch(?:'ine|ine)?)\b", lowered):
        return "main"
    if re.search(r"\bmaster(?:\s+dal(?:ına|ine)?|\s+branch(?:'ine|ine)?)\b", lowered):
        return "master"
    return None


def _positive_action_clauses(text: str) -> str:
    """Olumlu cümlecikleri koru, açık olumsuz talimatları at.

    ``repoyu pushla ama araç kullanma`` gerçek bir push isteği olarak KALIR: kullanıcı
    aracı yasaklamış olabilir ama istediği etki ortadan kalkmaz. Buna karşılık
    ``git kullanma; dosya oluştur`` yalnızca dosya cümleciğini bırakır.
    """
    clauses = [part.strip() for part in _ACTION_CLAUSE_SPLIT.split(text) if part.strip()]
    positive = [
        clause for clause in clauses if not any(word in clause for word in _NEGATED_ACTION_WORDS)
    ]
    return " ".join(positive)


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in patterns)
