"""Gözlem turu: soruyu cevaplar, çalışma alanına dokunmaz.

Neden var — ölçüldü (17 Eylül denetimi, iki ayrı koşu): kullanıcı sohbet kipinde
"bana bir kampanya planı yap" dedi. İstek "yap" kelimesi yüzünden karmaşık görev
sayıldı, plan motoruna girdi ve cevap sohbette gösterilmek yerine diske
`KAMPANYA_PLANI.md` olarak yazıldı. Aynı kipte "sadece 'merhaba' yaz" isteği de
dosya değişikliği sanılıp reddedildi.

Gözlem turu bir SORU turudur: model okuyabilir, arayabilir, web'e bakabilir; ama
dosya yazmaz, komut çalıştırmaz, commit atmaz. Bir şey değiştirilmesi gerekiyorsa
bunu cevabında söyler ve kullanıcı değişiklik isteyen bir görev verir.

`observe_execution` genel kuraldır; `chat_execution` onun sohbet kipine özel ince
sarmalayıcısıdır. Kod kipinde de aynı kilit uygulanır: turun metni yalnızca
`workspace_read` etkisi istiyorsa (bkz. `effects/detect.py`), model o turda da
yazamaz — kapsamı büyüten dürtme yerine kilit turun BAŞINDA konur.
"""

from __future__ import annotations

from dataclasses import replace

from ...tools.registry import ToolRegistry
from .execution_policy import ExecutionPolicy

__all__ = [
    "CHAT_MUTATION_REASON",
    "WORKSPACE_READ_REASON",
    "chat_execution",
    "chat_tool_names",
    "observe_execution",
]

#: Model bir değiştirme aracı çağırmaya kalkarsa görecek gerekçe (sohbet kipi).
CHAT_MUTATION_REASON = (
    "Sohbet kipindesin: dosya yazamaz, komut çalıştıramazsın. Cevabı burada ver; "
    "değişiklik gerekiyorsa kullanıcıya kod kipine geçmesini söyle."
)

#: Kod kipinde turun metni yalnızca okuma isterken model yazmaya kalkarsa görecek
#: gerekçe.
WORKSPACE_READ_REASON = "Bu tur salt okuma; değişiklik istiyorsan açıkça söyle."


def observe_execution(execution: ExecutionPolicy, reason: str) -> ExecutionPolicy:
    """Yürütme politikasını bir GÖZLEM turuna uyarla.

    Kanıt kapıları da kapatılır: gözlem turunda "dosya değiştirdiğini kanıtla"
    beklentisi turu haksız yere başarısız ilan ediyordu.
    """
    return replace(
        execution,
        allow_mutation=False,
        mutation_block_reason=reason,
        # Bu engel turun KARARIDIR, modelin yeteneği değil: yedek zinciri başka
        # bir modele düşse de gözlem turu yazmaya açılmaz.
        mutation_blocked_by_capability=False,
        requires_tool_evidence=False,
        required_effect=None,
        complex_task=False,
        observe_only=True,
    )


def chat_execution(execution: ExecutionPolicy) -> ExecutionPolicy:
    """Yürütme politikasını sohbet turuna uyarla (`observe_execution`'ın sarmalayıcısı)."""
    return observe_execution(execution, CHAT_MUTATION_REASON)


def chat_tool_names(registry: ToolRegistry) -> frozenset[str]:
    """Sohbet turunda sunulacak araçlar: yalnızca değiştirmeyenler.

    Liste sabit değil kayıt defterinden türetilir; yeni bir okuma aracı eklendiğinde
    burada iş çıkmaz, yeni bir değiştirme aracı da yanlışlıkla sohbete sızmaz.
    """
    okuyanlar = []
    for ad in registry.names():
        arac = registry.get(ad)
        if arac is not None and not arac.mutating:
            okuyanlar.append(ad)
    return frozenset(okuyanlar)
