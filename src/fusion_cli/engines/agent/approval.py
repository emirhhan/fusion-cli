"""Onay politikaları — "bu değişikliğe izin var mı?" sorusunun tek cevap yeri.

Beş kip tek bir protokolün arkasındadır (Claude'un izin kipleriyle aynı adlar);
motor hangi kipte olduğunu bilmez, yalnızca `decide` çağırır.

    auto      Fusion karar verir: projede iş gören her şey sorulmadan yapılır;
              yalnız riskli olan (proje dışı, sistem, yayın/push, uzak sunucu,
              dikkat gerektiren silme, uzak sistemde değişiklik) sorulur
    edits     dosya düzenlemeleri ve tanınan güvenli komutlar sorulmaz; kalan sorulur
    security  "Manuel": okuma dışındaki her işlem tek tek sorulur
    plan      düzenleme yok; okuma serbest; öteki kabuk komutu ve uzak değişiklik
              sorulur (`plan_approval`, #52)
    bypass    hiçbir şey sorulmaz (silinen yine Fusion çöpüne gider); tek istisna:
              uzak sistemde geri alınamaz etki bildiren araç her çağrıda sorulur

Yıkıcı komut (`danger`) auto, edits ve security kiplerinde DAİMA sorulur ve oturum
iznine dönüşmez: otomatik onay hız içindir, geri alınamaz bir işlemi sessizce
yapmak için değil. Sade `rm` yıkıcı sayılmaz — çöpe gider ve geri alınır.

İzin kuralları (P-001, `config/permission_rules.py`) kipten ÖNCE gelir ve karar sırası
sabittir (Claude gibi, #84): deny (her kipte, bypass dahil; sorulmaz) → ask (sorulur)
→ allow (sorulmaz; yalnız korumalı yol ve kritik yol silmesini açmaz) → kip → hafıza → soru.
Fusion'ın sezgisel yıkıcı (`danger`) sınıflandırması yalnız kuralsız çağrıda kipin önüne geçer.
Korumalı proje yolu (`.git/`, `.claude/`…) yıkıcı sayılır (P-002).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Collection
from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from ...config.permission_rules import PermissionDecision, PermissionRuleSet
from ...config.permissions import is_allowed
from ...core.desktop_settings import DesktopTarget
from ...core.errors import ConfigError
from ...core.tools import (
    AuthorizationScope,
    Tool,
    ToolArgs,
    ToolContext,
    ToolEffect,
    ToolFamily,
    tool_family,
)
from ...tools import desktop_policy
from ...tools.accept_edits_scope import accept_edits_allows
from ...tools.auto_policy import auto_risk, is_read_only_command
from ...tools.command_paths import escapes_project
from ...tools.command_policy import is_unattended_safe
from ...tools.critical_paths import critical_rm_reason, skip_critical_prompt
from ...tools.delete_preview import delete_caution, describe_delete, script_danger
from ...tools.outside_reads import read_roots
from ...tools.permission_match import RuleMatch, evaluate, writes_files
from ...tools.protected_paths import protected_path_reason
from ...tools.safe_delete import simple_rm_targets
from ...tools.safety import TRASHABLE_DELETE_REASONS, danger_reason
from ...tools.script_chain import script_chain_risk
from ...tools.write_targets import FILE_WRITE_TOOLS, write_targets
from .auto_guard import AutoReviewState
from .desktop_approval import apply_desktop, consent_description
from .plan_approval import PlanApproval
from .read_approval import mark_outside_read
from .sandbox_approval import apply_sandbox_policy
from .web_approval import adjust_web_request, web_scope

#: Uzak sistemde geri alınamaz değişiklik yapabilen aracın onay gerekçesi.
REMOTE_DESTRUCTIVE_REASON = (
    "Bu uzak araç kendini geri alınamaz değişiklik yapabilir olarak tanımlıyor "
    "(silme, yayınlama veya harcama). Her çağrıda ayrıca onay istenir."
)

#: Uzak sistemde değişiklik yapan aracın otomatik kipte sorulma gerekçesi.
REMOTE_WRITE_REASON = "uzak sistemde değişiklik yapıyor"

#: Kullanıcının girişli tarayıcı oturumunu ajana açan çağrının sorulma gerekçesi (P-023).
REMOTE_SESSION_REASON = (
    "girişli tarayıcı oturumunu (çerez profili) ajana açıyor; ajan bu sitelerde senin "
    "hesabınla gezinir"
)

#: Gözetimsiz ("Düzenlemeleri kabul et" kipinde sormadan) çalışabilecek etki sınıfları.
_UNATTENDED_EFFECTS = frozenset(
    {ToolEffect.LOCAL, ToolEffect.REMOTE_READ, ToolEffect.REMOTE_INTERACT}
)


class ApprovalMode(Enum):
    """Kullanıcının seçtiği onay politikası (Claude'un izin kipleri)."""

    AUTO = "auto"
    ACCEPT_EDITS = "edits"
    SECURITY = "security"
    PLAN = "plan"
    BYPASS = "bypass"
    DONT_ASK = "dontAsk"


#: Shift+Tab döngüsü (Claude'daki sıra). "İzinleri atla" BİLEREK yok: tek tuşla
#: yanlışlıkla açılmamalı; `/bypass` ile açıkça seçilir.
CYCLE_MODES = (
    ApprovalMode.AUTO,
    ApprovalMode.SECURITY,
    ApprovalMode.ACCEPT_EDITS,
    ApprovalMode.PLAN,
)


def next_mode(
    mode: ApprovalMode, *, bypass_available: bool = False, auto_available: bool = True
) -> ApprovalMode:
    """Shift+Tab döngüsünde sıradaki kip (Claude, #73/#85).

    Sıra: default → acceptEdits → plan → [bypassPermissions] → [auto] → default. Bypass
    yalnız oturum onunla (ya da `--allow-dangerously-skip-permissions`/kullanıcı ayarı
    `defaultMode: bypassPermissions` ile) başladıysa, auto yalnız `disableAutoMode` yoksa
    döngüdedir. dontAsk hiçbir zaman döngüde değildir.
    """
    cycle = [ApprovalMode.SECURITY, ApprovalMode.ACCEPT_EDITS, ApprovalMode.PLAN]
    if bypass_available:
        cycle.append(ApprovalMode.BYPASS)
    if auto_available:
        cycle.append(ApprovalMode.AUTO)
    if mode not in cycle:
        return cycle[0] if mode is ApprovalMode.AUTO or not auto_available else ApprovalMode.AUTO
    return cycle[(cycle.index(mode) + 1) % len(cycle)]


def may_run_unasked_commands(mode: ApprovalMode) -> bool:
    """Kip, onay sorusu olmadan arka plan komutu (dev sunucusu) çalıştırmaya izin verir mi?

    SECURITY ("okuma dışı her şey sorulur") ve PLAN (hiçbir değişiklik yok) vermez.
    """
    return mode not in (ApprovalMode.SECURITY, ApprovalMode.PLAN, ApprovalMode.DONT_ASK)


#: Kipin elle yazılabilen öteki adları (Claude'daki adlar dahil).
_MODE_ALIASES = {
    "dontask": ApprovalMode.DONT_ASK,
    "dont-ask": ApprovalMode.DONT_ASK,
    "manual": ApprovalMode.SECURITY,
    "manuel": ApprovalMode.SECURITY,
    "default": ApprovalMode.SECURITY,
    "accept-edits": ApprovalMode.ACCEPT_EDITS,
    "acceptedits": ApprovalMode.ACCEPT_EDITS,
    "bypass-permissions": ApprovalMode.BYPASS,
    "bypasspermissions": ApprovalMode.BYPASS,
}


def parse_mode(raw: str) -> ApprovalMode:
    """Kip adını çöz; bilinmiyorsa `ValueError`."""
    value = raw.strip().lower()
    return _MODE_ALIASES.get(value) or ApprovalMode(value)


#: Kiplerin sıkılık sırası (küçük = gevşek). Alt ajanın `permissionMode` alanı üst ajanın
#: kipini yalnız bu sırada YUKARI taşıyabilir (P-034): `bypass` miras alınmaz, `plan`
#: isteyen alt ajan auto kipteki üstten daha gevşek olamaz.
MODE_STRICTNESS: dict[ApprovalMode, int] = {
    ApprovalMode.BYPASS: 0,
    ApprovalMode.AUTO: 1,
    ApprovalMode.ACCEPT_EDITS: 2,
    ApprovalMode.SECURITY: 3,
    ApprovalMode.DONT_ASK: 3,
    ApprovalMode.PLAN: 4,
}


def strictest_mode(parent: ApprovalMode, requested: ApprovalMode | None) -> ApprovalMode:
    """Üst kip ile istenen kipten SIKI olanı döndür; istek yoksa üst kip."""
    if requested is None:
        return parent
    return requested if MODE_STRICTNESS[requested] > MODE_STRICTNESS[parent] else parent


class Decision(Enum):
    """Bir araç çağrısının akıbeti.

    `DENIED` ile `BLOCKED` ayrı tutulur: ilkinde kullanıcıya soruldu ve hayır dedi,
    ikincisinde politika gereği hiç sorulmadı. Model bu ikisine farklı tepki vermeli.
    """

    ALLOW = "allow"
    DENIED = "denied"
    BLOCKED = "blocked"


class ApprovalAnswer(Enum):
    """Etkileşimli onay ekranının daha zengin kullanıcı kararı."""

    ONCE = "once"
    SESSION = "session"
    #: Kalıcı kural: "bir daha sorma" (`permission_persist`); yalnız `can_persist` isteklerde.
    ALWAYS = "always"
    DENY = "deny"
    #: Kimseye SORULAMADI (oturum etkileşimsiz — TTY yok, boru hattı, CI).
    #:
    #: Kullanıcının gerçekten "hayır" demesiyle (`DENY`) KARIŞTIRILMAMALI: ikisi
    #: `Decision`de de ayrı sonuçlara gider (`_ask_and_remember`). Reddeden bir
    #: insan turu durdurur; sorulamayan bir oturum turu SÜRDÜRÜR ve modele başka
    #: bir yol denemesi söylenir.
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ApprovalReply:
    """Prompter'ın karar + isteğe bağlı kullanıcı notu cevabı (P-013).

    Enum değerleri korunur: not istemeyen prompter'lar `ApprovalAnswer`/`bool` döndürmeye
    devam eder. Ret notu modele araç sonucu olarak gider ve tur SÜRER; notsuz ret turu
    durdurur (bkz. `denial.py`).
    """

    answer: ApprovalAnswer | bool
    note: str = ""


@dataclass(frozen=True, slots=True)
class Denial:
    """`decide` sonucu: kullanıcı GEREKÇEYLE reddetti; model gerekçeyi görüp yolunu değiştirir."""

    note: str

    @property
    def decision(self) -> Decision:
        return Decision.DENIED


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """Onaya sunulan araç çağrısı."""

    tool: Tool
    args: ToolArgs
    #: Yıkıcı olduğu tespit edildiyse gerekçesi, değilse None.
    danger: str | None
    #: Kullanıcının izin listesinde (.claude/settings.local.json) mi?
    pre_allowed: bool = False
    #: Çağrı gözetimsiz çalışmaya uygun mu?
    #:
    #: Kabukta tanınan, yan etkisiz komut; kabuk dışında yerel ya da salt okunur
    #: uzak araç. Uzak yazma araçları False'tur ve auto kipte sorulur.
    unattended_safe: bool = True
    #: Bu ÇAĞRININ etkisi (araç ağ geçidiyse yeteneğe göre çözülmüş olabilir).
    effect: ToolEffect = ToolEffect.LOCAL
    #: Otomatik kipte neden sorulduğu; None ise otomatik kip sormaz (`auto_policy`).
    risk: str | None = None
    #: Çağrı YALNIZ okuyor mu? Manuel kip sormaz, plan kipi izin verir.
    read_only: bool = False
    #: Onay kartında gösterilecek ek bilgi (silme hedefi, sorulma nedeni).
    note: str | None = None
    authorization_scope: AuthorizationScope | None = None
    #: Dosya yazma aracı proje (ve `--add-dir`) DIŞINA yazıyorsa hedefin dizini.
    #:
    #: Oturum izni bu dizine bağlanır: proje içi `write_file` izni `~/.zshrc`'yi
    #: kapsamaz (A1-06).
    outside_dir: str | None = None
    #: İsteği yapan alt ajanın etiketi (`Geliştirici (kodcu-3f9a1c)`); ana ajanda boş.
    #: Onay kartı, terminal ve uzak bildirim "kim istiyor"u bununla gösterir (P-034).
    agent_label: str = ""
    #: `deny` kuralı ya da kök-dışı engel çağrıyı sorulmadan kapattıysa gerekçesi (P-001/P-002).
    pre_denied: str | None = None
    #: Bir `ask` kuralı eşleştiyse gerekçesi: kip ne olursa olsun sorulur.
    pre_ask: str | None = None
    #: Eşleşen izin kuralının yazımı (`Bash(npm run *)`); kartta gösterilir.
    rule: str | None = None
    #: Masaüstü eyleminin hedef uygulaması (P-007); kart "Mail · tam kontrol" gösterir.
    desktop_target: DesktopTarget | None = None
    #: Araçtan bağımsız oturum izni anahtarı (uygulama başına masaüstü onayı, P-007).
    consent_key: str | None = None
    #: `pre_denied` masaüstü politikasından geliyor (modele masaüstü engel metni döner).
    desktop_blocked: bool = False
    #: Tanınan kritik yol `rm`/`rmdir` silmesi (#42): bypass dahil hiçbir kip sormadan geçirmez.
    critical: str | None = None
    #: Kabuk komutu acceptEdits kapsamında mı (#53)? Kabuk dışı çağrıda `None`.
    accept_edits_ok: bool | None = None
    #: Korumalı yol gerekçesi (`.git/`, `.claude/`…); allow kuralı bunu açmaz (#84).
    protected: str | None = None

    @property
    def rule_opens(self) -> bool:
        """Allow kuralı çağrıyı açıyor mu (#84)? Claude: deny → ask → allow; allow kuralı
        yalnız korumalı yolları ve kritik yol silmelerini açmaz, Fusion'ın sezgisel
        `danger` sınıflandırması allow'un önüne geçmez."""
        return (
            self.pre_allowed
            and self.pre_ask is None
            and self.critical is None
            and self.protected is None
        )

    @property
    def can_remember(self) -> bool:
        """Yalnız doğrulanmış dar kapsam oturum boyunca saklanır.

        `ask` kuralı eşleşen istek hatırlanmaz: kural "her zaman sor" der (Claude'da da
        ask daima sorar). Ölçüldü (31 Ekim): kart 'bu oturumda tekrar sorma' sunuyor ve
        ikinci `git push` sorulmadan geçiyordu.
        """
        return self.danger is None and self.pre_ask is None and _scope(self) is not None

    @property
    def offers_session(self) -> bool:
        """Kartta "bu oturumda sorma" seçeneği var mı (#82)? Claude'da kabuk komutunda
        yalnız kalıcı "Yes, and don't ask again" sunulur; kalıcı kural yazılamıyorsa oturum."""
        if not self.can_remember:
            return False
        return not (tool_family(self.tool.name) is ToolFamily.SHELL and self.can_persist)

    @property
    def can_persist(self) -> bool:
        """ "Bir daha sorma" kalıcı kuralı sunulabilir mi? (P-003)

        Yıkıcı, uzak ve `ask` kurallı istekte sunulmaz: yıkıcı işlem kalıcı izne dönüşmez,
        uzak araç kapsamı dosyada ifade edilemez, `ask` kuralı zaten allow'dan üstündür.
        """
        return (
            self.danger is None
            and self.pre_ask is None
            and self.effect is ToolEffect.LOCAL
            and tool_family(self.tool.name) is not ToolFamily.EXTERNAL
            # Claude (#68): dosya düzenleme onayı yalnız oturum sonuna dek geçerlidir.
            and self.tool.name not in FILE_WRITE_TOOLS
        )

    @property
    def remembered_scope_description(self) -> str | None:
        """Uzak oturum iznini tüm arayüzlerde aynı açık kapsamla anlat."""
        desktop = consent_description(self)
        if desktop is not None and self.can_remember:
            return desktop
        scope = self.authorization_scope
        if (
            not self.can_remember
            or self.effect is ToolEffect.LOCAL
            or tool_family(self.tool.name) is ToolFamily.SHELL
            or scope is None
            or not scope.is_complete
        ):
            return None
        targets = ", ".join(repr(target) for target in sorted(set(scope.targets)))
        return (
            f"Yalnız bu kapsam: sunucu {scope.server!r}; hesap {scope.account!r}; "
            f"eylem {scope.action!r}; hedefler {targets}. "
            "Hesap, eylem veya hedef değişirse yeniden sorulur."
        )


class Prompter(Protocol):
    """Kullanıcıya evet/hayır sorabilen taraf. Motor terminali böyle görmez."""

    async def confirm(self, request: ApprovalRequest) -> bool | ApprovalAnswer | ApprovalReply: ...


class ApprovalPolicy(Protocol):
    """Bir araç çağrısına izin verilip verilmeyeceğine karar verir."""

    async def decide(self, request: ApprovalRequest) -> Decision | Denial: ...


class ApprovalMemory:
    """Kullanıcının "oturum boyunca" dediği izinleri turlar arasında taşır.

    Politika her kullanıcı turunda `build_policy` ile yeniden kurulur; izin kümesi
    politikanın içinde yaşadığında tur bitince kayboluyor ve kullanıcı aynı araç
    için her mesajda yeniden soruluyordu. Hafızanın sahibi uzun ömürlü sohbet
    durumudur (`ReplState`); politika yalnızca onu kullanır.

    Yıkıcı çağrılar (`danger` dolu) hiçbir zaman hatırlanmaz.
    """

    def __init__(self) -> None:
        self._scopes: set[str] = set()
        self.revision = 0
        #: "Bir daha sorma" kararını kalıcı kurala yazan taraf (sahip bağlar; P-003).
        #: Çağrı başarısızlığı `ConfigError` fırlatır; kullanıcıya `notices` ile söylenir.
        self.rule_writer: Callable[[ApprovalRequest], str] | None = None
        #: Kullanıcıya gösterilecek bekleyen bildirimler (kural yazıldı / yazılamadı).
        self.notices: list[str] = []
        #: Otomatik kip denetçisinin oturum durumu: engel sayaçları, kip düşüşü (P-011).
        self.auto_review = AutoReviewState(remembered=self.is_remembered)
        #: Bypass kullanılabilir oturum: plan kipinde de soru/sınıflandırıcı yok (#52).
        self.plan_bypass = False

    def take_notices(self) -> list[str]:
        notices, self.notices = self.notices, []
        return notices

    def revoke(self) -> None:
        """Oturum izinlerini açıkça geri al."""
        self._scopes.clear()
        self.revision += 1

    def is_remembered(self, request: ApprovalRequest) -> bool:
        """Bu çağrı için daha önce oturum izni verildi mi?"""
        scope = _scope(request)
        return request.danger is None and scope is not None and scope in self._scopes

    def remember(self, request: ApprovalRequest) -> None:
        """Oturum iznini kaydet; yıkıcı çağrı sessizce dışarıda bırakılır."""
        scope = _scope(request)
        if request.danger is None and scope is not None:
            self._scopes.add(scope)


class _AskingApproval:
    """Kipin serbest bıraktığını sormadan geçirir, kalanı sorar ve hatırlar.

    Yıkıcı (`danger`) çağrı hiçbir kipte serbest değildir; kullanıcının izin
    listesindeki komut (`pre_allowed`) her soran kipte serbesttir.
    """

    def __init__(self, prompter: Prompter, memory: ApprovalMemory | None = None) -> None:
        self._prompter = prompter
        self._memory = memory if memory is not None else ApprovalMemory()

    def _allows(self, request: ApprovalRequest) -> bool:
        raise NotImplementedError

    async def decide(self, request: ApprovalRequest) -> Decision | Denial:
        if request.pre_denied is not None:
            # `deny` kuralı / kök-dışı engel: kimseye sorulmaz, model gerekçeyi görür.
            return Decision.BLOCKED
        if request.rule_opens or (
            request.danger is None and request.pre_ask is None and self._allows(request)
        ):
            return Decision.ALLOW
        if request.pre_ask is None and self._memory.is_remembered(request):
            return Decision.ALLOW
        return await _ask_and_remember(self._prompter, request, self._memory)


class AutoApproval(_AskingApproval):
    """Otomatik: Fusion karar verir, yalnız RİSKLİ olanı sorar (`auto_policy`).

    Eskiden beyaz listeye bakıyordu ve `php -l`, `lsof`, `unzip` gibi sıradan
    komutlarda bile soruyordu; kullanıcı (2 Ekim) "gereksiz yerlerde soru
    soruyor, sormasın" dedi. Beyaz liste artık "Düzenlemeleri kabul et" kipidir.
    """

    def __init__(self, prompter: Prompter, memory: ApprovalMemory | None = None) -> None:
        super().__init__(prompter, memory)
        guard = self._memory.auto_review
        #: Kurulduğu andaki düşüş sayısı; tur ortasında denetçi kipi düşürürse (P-011) bu
        #: politika kalan çağrılarda Manuel gibi davranır.
        self._trips = guard.trips
        if guard.on_fallback is not None:
            # Sahip düşüşte kipi Manuel'e çeker; Otomatik politika kuruluyorsa kip yeniden
            # seçilmiştir. Sahipsiz (`fusion run`) düşüş kalıcıdır: alt ajanın yeni
            # politikası onu silmemeli (ölçüldü, 31 Ekim).
            guard.acknowledge_auto()

    def _allows(self, request: ApprovalRequest) -> bool:
        guard = self._memory.auto_review
        if guard.trips != self._trips or (guard.fell_back and guard.on_fallback is None):
            return request.read_only
        return request.risk is None


class AcceptEditsApproval(_AskingApproval):
    """Düzenlemeleri kabul et: dosya düzenlemeleri ve tanınan güvenli komutlar serbest."""

    def _allows(self, request: ApprovalRequest) -> bool:
        # Kabukta Claude kapsamı (#53): 7 dosya sistemi komutu çalışma dizinlerinde + salt okuma.
        if request.accept_edits_ok is not None:
            return request.accept_edits_ok
        return request.unattended_safe


class SecurityApproval(_AskingApproval):
    """Manuel: okuma dışındaki her işlem tek tek sorulur.

    İstisna: kullanıcının kendi izin listesine yazdığı komutlar sorulmaz — kullanıcı
    o kararı zaten vermiştir. Yıkıcı komutlar bu istisnadan yararlanamaz.
    """

    def _allows(self, request: ApprovalRequest) -> bool:
        return request.read_only


class DontAskApproval:
    """Açık izinleri ve okumayı koru; kullanıcı etkileşimi gereken çağrıyı reddet."""

    async def decide(self, request: ApprovalRequest) -> Decision | Denial:
        if request.pre_denied is None and request.rule_opens:
            return Decision.ALLOW
        if (
            request.pre_denied is not None
            or request.pre_ask is not None
            or request.danger is not None
            or request.tool.name == "ask_user"
            or request.effect is ToolEffect.REMOTE_SESSION
        ):
            return Decision.BLOCKED
        if request.read_only:
            return Decision.ALLOW
        return Decision.BLOCKED


class BypassApproval:
    """İzinleri atla: neredeyse hiçbir şey sorulmaz. Sade `rm` yine çöpe gider (`shell`).

    TEK sert tavan (A1-08): uzak sistemde GERİ ALINAMAZ etki bildiren araç
    (`REMOTE_DESTRUCTIVE`: silme, yayınlama, harcama) bypass'ta bile her çağrıda son
    kez sorulur ve oturum iznine dönüşmez. Yerel komutlar (git push, sudo vb.)
    kullanıcının bilinçli seçimi olarak serbest kalır. Kullanıcının kendi yazdığı
    `deny` kuralı bypass'ta da geçerlidir (Claude: deny her kipte; P-001).
    """

    def __init__(
        self, prompter: Prompter | None = None, memory: ApprovalMemory | None = None
    ) -> None:
        self._prompter = prompter
        self._memory = memory if memory is not None else ApprovalMemory()

    async def decide(self, request: ApprovalRequest) -> Decision | Denial:
        if request.pre_denied is not None:
            return Decision.BLOCKED
        # Claude: açık `ask` kuralı ve kritik yol silmesi bypass'ta da sorulur (#42).
        # Sandbox dışı çalıştırma isteği de `pre_ask` taşır ama kural değildir: bypass sormaz.
        explicit_ask = (
            request.pre_ask is not None and request.rule is not None and not request.pre_allowed
        )
        must_ask = explicit_ask or (request.critical is not None and not skip_critical_prompt())
        if self._prompter is None:
            return Decision.BLOCKED if must_ask else Decision.ALLOW
        if not must_ask and request.effect is not ToolEffect.REMOTE_DESTRUCTIVE:
            return Decision.ALLOW
        return await _ask_and_remember(self._prompter, request, self._memory)


def build_policy(
    mode: ApprovalMode, prompter: Prompter, memory: ApprovalMemory | None = None
) -> ApprovalPolicy:
    """Moda karşılık gelen politikayı üret.

    `memory` verilmezse tek turluk taze hafıza kurulur; sohbet boyunca yaşayan
    çağıranlar kendi hafızalarını her turda aynı nesneyle geçirir.
    """
    if mode is ApprovalMode.DONT_ASK:
        return DontAskApproval()
    if mode is ApprovalMode.PLAN:
        return PlanApproval(prompter, memory)
    if mode is ApprovalMode.BYPASS:
        return BypassApproval(prompter, memory)
    if mode is ApprovalMode.SECURITY:
        return SecurityApproval(prompter, memory)
    if mode is ApprovalMode.ACCEPT_EDITS:
        return AcceptEditsApproval(prompter, memory)
    return AutoApproval(prompter, memory)


async def resolve_request(
    tool: Tool,
    args: ToolArgs,
    allowed_commands: frozenset[str] = frozenset(),
    *,
    root: Path | None = None,
    context: ToolContext | None = None,
    rules: PermissionRuleSet | None = None,
) -> ApprovalRequest:
    """Onay isteğini, araç çağrı bazlı etki bildiriyorsa o etkiyle kur.

    Çözücü `None` dönerse ya da yoksa aracın kendi etkisi geçerlidir.
    """
    effect = await tool.effect_resolver(args, context) if tool.effect_resolver is not None else None
    touched = context.touched if context is not None else ()
    extra_roots = tuple(context.extra_roots) if context is not None else ()
    request = build_request(
        tool,
        args,
        allowed_commands,
        effect=effect,
        root=root,
        touched=touched,
        extra_roots=extra_roots,
        rules=rules,
    )
    # Çalışma dizinleri dışından okuma (#56): Manuel/acceptEdits/plan sorar.
    request = mark_outside_read(
        request,
        root,
        read_roots(context),
        blocked=bool(getattr(context, "block_reads_outside_root", False)),
    )
    # Sandbox dışı istek her seferinde sorulur; sandbox'lı komut auto_allow ile serbest (P-010).
    request = apply_sandbox_policy(request, context)
    if context is None or tool_family(tool.name) is not ToolFamily.DESKTOP:
        return request
    # Masaüstü: hedef uygulama, kademe, oturum onayı ve riskli eylem (P-007, P-008).
    assessment = await desktop_policy.assess(tool.name, args, context)
    return apply_desktop(request, assessment, consent=context.desktop_settings.app_consent)


def build_request(
    tool: Tool,
    args: ToolArgs,
    allowed_commands: frozenset[str] = frozenset(),
    *,
    effect: ToolEffect | None = None,
    root: Path | None = None,
    touched: Collection[Path] = (),
    extra_roots: tuple[Path, ...] = (),
    rules: PermissionRuleSet | None = None,
) -> ApprovalRequest:
    """Onay isteğini kur; yıkıcılık, risk ve izin listesi kontrolü burada yapılır.

    Uzak araçlar kabuk komutu gibi ele alınır: bir reklam MCP'sinin bütçe değiştiren
    aracı (REMOTE_WRITE) otomatik kipte sorulur; okuyan ve sayfayla etkileşen araç
    sorulmaz. `rules` verilirse izin kuralları (P-001) ve kök-dışı engeller (P-002) uygulanır.
    """
    command = args.get("command")
    # Sınıflandırma TEK KAYNAKTAN (`core.tools.tool_family`) okunur: birebir ad
    # karşılaştırması `bash`/`shell`/`execute_command` takma adıyla çağrılan bir
    # kabuk komutunu kaçırır ve onun güvenlik/izin-listesi denetimini atlardı.
    effect = effect or tool.effect
    match = evaluate(rules, tool.name, args, root) if rules is not None else None
    if tool_family(tool.name) is ToolFamily.SHELL and isinstance(command, str):
        request = _shell_request(
            tool, args, command, allowed_commands, effect, root, touched, rules=rules
        )
        request = replace(request, accept_edits_ok=accept_edits_allows(command, root, extra_roots))
        critical = critical_rm_reason(command, root, extra_roots) if root is not None else None
        if critical is not None:
            # Allow kuralı ve oturum izni kritik yol silmesini açmaz (#42, #84).
            request = replace(request, critical=critical, danger=request.danger or critical)
        return _apply_rule(request, match)
    danger = danger_reason(tool.name, args)
    if danger is None and effect is ToolEffect.REMOTE_DESTRUCTIVE:
        danger = REMOTE_DESTRUCTIVE_REASON
    # Korumalı proje yolu (`.git/`, `.claude/`…): her kipte sorulur, hatırlanmaz (P-002).
    protected = protected_path_reason(tool.name, args, root)
    danger = danger or protected
    risk = None if effect in _UNATTENDED_EFFECTS else _remote_risk(effect)
    unattended_safe = effect in _UNATTENDED_EFFECTS
    # Yerel dosya aracı proje DIŞINA yazıyorsa risklidir (modül belgesi: "proje dışı
    # sorulur"). Eskiden bu yalnız kabukta uygulanıyordu; `write_file ~/.zshrc`
    # auto kipte sorulmuyor, "oturum boyunca" izni de araç adına bağlı olduğundan
    # sonraki her yolu kapsıyordu. Ölçüldü (29 Ekim, A1-06).
    outside_dir = _outside_write_dir(tool, args, root, extra_roots) if risk is None else None
    pre_denied = None
    if outside_dir is not None:
        hedef = next(iter(write_targets(tool.name, args)), args.get("path"))
        risk = f"proje dışına yazıyor ({hedef})"
        unattended_safe = False
        if rules is not None and rules.block_writes_outside_root:
            # Kapı kapalı: sormak anlamsız, model `--add-dir` ile açılabileceğini öğrenir.
            pre_denied = OUTSIDE_WRITE_BLOCKED.format(yol=hedef)
    request = ApprovalRequest(
        tool=tool,
        args=args,
        danger=danger,
        unattended_safe=unattended_safe,
        effect=effect,
        risk=risk,
        read_only=effect is ToolEffect.REMOTE_READ,
        note=risk,
        authorization_scope=tool.scope_resolver(args) if tool.scope_resolver is not None else None,
        outside_dir=outside_dir,
        pre_denied=pre_denied,
        protected=protected,
    )
    return adjust_web_request(_apply_rule(request, match))


#: Kök-dışı yazma engeli açıkken (P-002) modele dönen gerekçe.
OUTSIDE_WRITE_BLOCKED = (
    "proje kökü dışına yazma kapalı (ayar: runtime.block_writes_outside_root): {yol}. "
    "Gerekiyorsa kullanıcı `--add-dir <dizin>` ile ya da Ayarlar › İzinler'den açar"
)


def _apply_rule(request: ApprovalRequest, match: RuleMatch | None) -> ApprovalRequest:
    """Kural kararını isteğe işle: deny → pre_denied, ask → pre_ask, allow → pre_allowed."""
    if match is None:
        return request
    pattern = match.rule.pattern
    if match.decision is PermissionDecision.DENY:
        reason = f"izin kuralı yasaklıyor: {pattern} ({match.rule.source or 'kural'})"
        return replace(request, pre_denied=request.pre_denied or reason, rule=pattern)
    if match.decision is PermissionDecision.ASK:
        reason = f"izin kuralı her zaman sorulmasını istiyor: {pattern}"
        return replace(request, pre_ask=reason, rule=pattern, note=request.note or reason)
    return replace(request, pre_allowed=True, rule=pattern)


def _remote_risk(effect: ToolEffect) -> str:
    """Gözetimsiz çalışamayan etkinin onay kartındaki gerekçesi."""
    if effect is ToolEffect.REMOTE_SESSION:
        return REMOTE_SESSION_REASON
    return REMOTE_WRITE_REASON


def _outside_write_dir(
    tool: Tool, args: ToolArgs, root: Path | None, extra_roots: tuple[Path, ...]
) -> str | None:
    """Dosya yazma aracının hedefi kök (+ `--add-dir`) dışındaysa hedefin dizini.

    Yazan araç listesi `write_targets` ile ortaktır (A1-06, P-002): `download_file`,
    `extract_archive` ve görsel araçları da proje dışına yazıyorsa sorulur.
    """
    if root is None:
        return None
    targets = write_targets(tool.name, args)
    if not targets:
        return None
    raw = targets[0]
    try:
        path = Path(raw).expanduser()
        target = (path if path.is_absolute() else root / path).resolve()
        allowed = (root.resolve(), *(extra.resolve() for extra in extra_roots))
    except (OSError, RuntimeError, ValueError):
        # Çözümlenemeyen yol güvenli tarafta DIŞARIDA sayılır.
        return str(raw)
    if any(target == base or base in target.parents for base in allowed):
        return None
    return str(target.parent)


def _shell_request(
    tool: Tool,
    args: ToolArgs,
    command: str,
    allowed_commands: frozenset[str],
    effect: ToolEffect,
    root: Path | None,
    touched: Collection[Path] = (),
    *,
    rules: PermissionRuleSet | None = None,
) -> ApprovalRequest:
    """Kabuk komutunun onay isteği: kart komutu değil SONUCU göstermeli.

    Kök-dışı yazma engeli (P-002) kabuk yönlendirmesini de kapatır: `echo x > ~/.zshrc`,
    `| tee /etc/hosts`. Ölçüldü (31 Ekim): engel yalnız dosya araçlarında uygulanıyordu;
    Ayarlar'daki "onay bile sorulmadan engellenir" sözü kabukta tutmuyordu.
    """
    danger = danger_reason(tool.name, args)
    trashed = simple_rm_targets(command) is not None
    if trashed and danger in TRASHABLE_DELETE_REASONS:
        # Sade `rm` kalıcı silmez, Fusion çöpüne taşır (`shell._guarded_delete`).
        danger = None
    home = Path.home()
    if danger is None and root is not None:
        danger = script_danger(command, root, home)
    protected = protected_path_reason(tool.name, args, root, is_shell=True)
    danger = danger or protected
    caution = delete_caution(command, root, home) if root is not None else None
    target = describe_delete(command, root, home) if root is not None else ""
    chain = script_chain_risk(command, root, touched)
    risk = caution or auto_risk(command, root) or chain
    if danger is not None and target:
        danger = f"{danger}. {target}"
    note = ". ".join(part for part in (risk, target) if part) or None
    pre_denied = None
    if rules is not None and rules.block_writes_outside_root and root is not None:
        disari = _outside_write_targets(command, root)
        if disari:
            pre_denied = OUTSIDE_WRITE_BLOCKED.format(yol=disari[0])
    return ApprovalRequest(
        tool=tool,
        args=args,
        danger=danger,
        # Tek kural motoru (#86): kural kümesi varsa Bash allow kararını yalnız
        # `permission_match.evaluate` verir; eski birebir liste yalnız kuralsız çağıranda.
        pre_allowed=rules is None and is_allowed(command, allowed_commands),
        unattended_safe=(trashed and caution is None)
        or (chain is None and is_unattended_safe(command, root)),
        effect=effect,
        risk=risk,
        read_only=is_read_only_command(command),
        note=note,
        pre_denied=pre_denied,
        protected=protected,
    )


def _outside_write_targets(command: str, root: Path) -> tuple[str, ...]:
    """Komutun yönlendirme/`tee` ile proje kökü DIŞINA yazdığı hedefler.

    Bilinmeyen değişken (`> $OUT`) dışarı sayılmaz (`auto_policy._outside` ile aynı kural);
    `$HOME`/`~` ve mutlak/`..` yollar sayılır.
    """
    return tuple(
        target
        for target in writes_files(command)
        if ("$" not in target or "$HOME" in target or "${HOME" in target)
        and escapes_project("tee", [target], root)
    )


async def _ask_and_remember(
    prompter: Prompter,
    request: ApprovalRequest,
    memory: ApprovalMemory,
) -> Decision | Denial:
    revision = memory.revision
    reply = await prompter.confirm(request)
    answer, note = (
        (reply.answer, reply.note.strip()) if isinstance(reply, ApprovalReply) else (reply, "")
    )
    if memory.revision != revision:
        return Decision.BLOCKED
    if answer is ApprovalAnswer.ALWAYS:
        # Kalıcı kural (P-003): bu oturumda da hatırlanır; dosyaya yazılamazsa izin
        # yine verilir (kullanıcı evet dedi) ama kaydedilemediği söylenir.
        memory.remember(request)
        if request.can_persist and memory.rule_writer is not None:
            try:
                memory.notices.append(memory.rule_writer(request))
            except ConfigError as error:
                memory.notices.append(str(error))
        return Decision.ALLOW
    if answer is ApprovalAnswer.SESSION:
        # Yıkıcı işlemler hiçbir zaman oturum iznine dönüşmez (`remember` bunu
        # uygular). UI bu seçeneği zaten göstermez; ikinci savunma hattı özel
        # prompter'ları da kapsar.
        memory.remember(request)
        return Decision.ALLOW
    if answer is ApprovalAnswer.ONCE or answer is True:
        return Decision.ALLOW
    if answer is ApprovalAnswer.UNAVAILABLE:
        # Kimseye SORULAMADI — bu insanın "hayır" demesiyle AYNI şey değildir.
        # `BLOCKED`, model açısından "bu yoldan olmaz, başka dene" demektir ve
        # turu durdurmaz; `DENIED` ise artık YALNIZCA gerçek bir insan reddini
        # taşır ve turu durdurur (bkz. `engines/agent/denial.py`, `loop._drive`).
        return Decision.BLOCKED
    if note:
        # Gerekçeli ret (P-013): model gerekçeyi araç sonucu olarak görür, tur sürer.
        return Denial(note)
    return Decision.DENIED


def _scope(request: ApprovalRequest) -> str | None:
    """Oturum izninin dar kapsamı: araç, aynı shell komutu ya da dışarıdaki dizin.

    Kabuk ailesi TEK KAYNAKTAN (`core.tools.tool_family`) tanınır ve kapsam
    anahtarı her zaman kanonik `run_shell:` öneki ile üretilir: aksi hâlde
    `bash` takma adıyla verilen bir oturum izni `run_shell:komut` anahtarından
    farklı bir anahtara düşer, komuta özgü daralma kaybolur ve izin aracın TÜM
    komutlarını kapsayacak kadar genişler.
    """
    if tool_family(request.tool.name) is ToolFamily.SHELL:
        return f"run_shell:{str(request.args.get('command', '')).strip()}"
    web = web_scope(request)
    if web is not None:
        # WebFetch alan başına, WebSearch araç başına (#55).
        return web
    if request.consent_key is not None:
        # Uygulama başına masaüstü onayı: aynı uygulamada tıklama ve yazma tek izindir.
        return request.consent_key
    if request.outside_dir is not None:
        # Proje DIŞINA yazan dosya aracı: izin yalnız bu dizine verilir.
        return f"{request.tool.name}:{request.outside_dir}"
    if request.effect is not ToolEffect.LOCAL:
        # Adaptör doğrulanmış kapsam sağlamıyorsa uzak izin yalnız bu çağrı içindir.
        scope = request.authorization_scope
        if scope is None or not scope.is_complete:
            return None
        identity = (
            request.tool.name,
            request.effect.value,
            scope.server,
            scope.account,
            scope.action,
            sorted(set(scope.targets)),
        )
        return sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
    return request.tool.name
