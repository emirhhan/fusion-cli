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
_ACTION_CLAUSE_SPLIT = re.compile(
    r"(?:[.!?;\n]+|\b(?:ama|fakat|ancak|lakin|ve|veya|ardından|ardindan|sonra)\b)",
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
        r"\b(?:komut|script|servis|sunucu|server|uygulama)[a-zçğıöşü]*.{0,40}\b"
        r"(?:çalıştır|calistir|başlat|baslat|durdur|yeniden başlat|restart)\b"
    ),
)
_FILE_MUTATION_PATTERNS = (
    (
        r"\b(?:dosya|klasör|klasor|dizin|kod|proje)[a-zçğıöşü]*.{0,50}\b"
        r"(?:sil|kaldır|kaldir|taşı|tasi|kopyala|yeniden adlandır|"
        r"yeniden adlandir|değiştir|degistir|düzenle|duzenle|"
        r"oluştur|olustur|ekle)\b"
    ),
    r"\b(?:sil|kaldır|kaldir|taşı|tasi|kopyala|yeniden adlandır|yeniden adlandir)\b",
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
    "ve", "ile", "sonra", "ardından", "ardindan", "önce", "once",
    "remote", "adres", "adresini", "adreslerini", "kontrol", "et",
    "push", "pushla", "pushlamak", "repo", "repository", "depo",
    "aktif", "mevcut", "uzak", "hedef", "olan", "olarak", "için", "icin",
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
        clause
        for clause in clauses
        if not any(word in clause for word in _NEGATED_ACTION_WORDS)
    ]
    return " ".join(positive)


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in patterns)
