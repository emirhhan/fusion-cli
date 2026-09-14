"""Onay politikaları — "bu değişikliğe izin var mı?" sorusunun tek cevap yeri.

Üç mod tek bir protokolün arkasındadır; motor hangi modda olduğunu bilmez, yalnızca
`decide` çağırır. Yeni bir mod eklemek yeni bir sınıf yazmaktır.

    auto      değiştirici işlemlere otomatik evet — AMA yıkıcı komutta yine sorar
    plan      hiçbir değişikliğe izin yok; yalnızca keşif ve plan
    security  her değiştirici işlem tek tek sorulur

`auto` modunun yıkıcı komutlarda bile sorması bilinçlidir: otomatik onay hız içindir,
geri alınamaz bir işlemi sessizce yapmak için değil.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from ...config.permissions import is_allowed
from ...core.tools import Tool, ToolArgs, ToolEffect
from ...tools.command_policy import is_unattended_safe
from ...tools.safety import danger_reason

#: Uzak sistemde geri alınamaz değişiklik yapabilen aracın onay gerekçesi.
REMOTE_DESTRUCTIVE_REASON = (
    "Bu uzak araç kendini geri alınamaz değişiklik yapabilir olarak tanımlıyor "
    "(silme, yayınlama veya harcama). Her çağrıda ayrıca onay istenir."
)

#: Gözetimsiz (auto kipte sormadan) çalışabilecek etki sınıfları.
_UNATTENDED_EFFECTS = frozenset({ToolEffect.LOCAL, ToolEffect.REMOTE_READ})


class ApprovalMode(Enum):
    """Kullanıcının seçtiği onay politikası."""

    AUTO = "auto"
    PLAN = "plan"
    SECURITY = "security"


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
    DENY = "deny"


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


class Prompter(Protocol):
    """Kullanıcıya evet/hayır sorabilen taraf. Motor terminali böyle görmez."""

    async def confirm(self, request: ApprovalRequest) -> bool | ApprovalAnswer: ...


class ApprovalPolicy(Protocol):
    """Bir araç çağrısına izin verilip verilmeyeceğine karar verir."""

    async def decide(self, request: ApprovalRequest) -> Decision: ...


class AutoApproval:
    """Değiştirici işlemlere otomatik evet; yıkıcı ve TANINMAYAN komutlarda sorar.

    Karar eskiden yalnızca `danger`'a bakıyordu: tehlike kalıbına uymayan her kabuk
    komutu sessizce çalışıyordu. Kalıp listesi ne kadar uzasa da `node -e`, hazır
    bir script ya da `>` ile dosya sıfırlama gibi yollar dışarıda kalıyordu.
    Artık kabuk için soru terstir — tanımadığımız komut sorulur (`command_policy`).
    """

    def __init__(self, prompter: Prompter) -> None:
        self._prompter = prompter
        self._session_allowed: set[str] = set()

    async def decide(self, request: ApprovalRequest) -> Decision:
        if request.danger is None and request.unattended_safe:
            return Decision.ALLOW
        if request.danger is None and _scope(request) in self._session_allowed:
            return Decision.ALLOW
        return await _ask_and_remember(self._prompter, request, self._session_allowed)


class SecurityApproval:
    """Her değiştirici işlemi tek tek sorar.

    İstisna: kullanıcının kendi izin listesine yazdığı komutlar sorulmaz — kullanıcı
    o kararı zaten vermiştir. Yıkıcı komutlar bu istisnadan yararlanamaz.
    """

    def __init__(self, prompter: Prompter) -> None:
        self._prompter = prompter
        self._session_allowed: set[str] = set()

    async def decide(self, request: ApprovalRequest) -> Decision:
        if request.pre_allowed and request.danger is None:
            return Decision.ALLOW
        if request.danger is None and _scope(request) in self._session_allowed:
            return Decision.ALLOW
        return await _ask_and_remember(self._prompter, request, self._session_allowed)


class PlanApproval:
    """Plan modu: hiçbir değişikliğe izin verilmez, kullanıcıya da sorulmaz."""

    async def decide(self, request: ApprovalRequest) -> Decision:
        return Decision.BLOCKED


def build_policy(mode: ApprovalMode, prompter: Prompter) -> ApprovalPolicy:
    """Moda karşılık gelen politikayı üret."""
    if mode is ApprovalMode.PLAN:
        return PlanApproval()
    if mode is ApprovalMode.SECURITY:
        return SecurityApproval(prompter)
    return AutoApproval(prompter)


def build_request(
    tool: Tool, args: ToolArgs, allowed_commands: frozenset[str] = frozenset()
) -> ApprovalRequest:
    """Onay isteğini kur; yıkıcılık tespiti ve izin listesi kontrolü burada yapılır.

    Uzak araçlar kabuk komutu gibi ele alınır: auto kip TANIMADIĞI şeyi sormadan
    yapmaz. Eskiden kabuk dışındaki her araç `unattended_safe=True` sayılıyordu;
    bir reklam MCP'sinin bütçe değiştiren aracı auto kipte kullanıcı görmeden
    çalışabiliyordu.
    """
    command = args.get("command")
    kabuk = tool.name == "run_shell" and isinstance(command, str)
    pre_allowed = kabuk and is_allowed(str(command), allowed_commands)
    danger = danger_reason(tool.name, args)
    if danger is None and tool.effect is ToolEffect.REMOTE_DESTRUCTIVE:
        danger = REMOTE_DESTRUCTIVE_REASON
    return ApprovalRequest(
        tool=tool,
        args=args,
        danger=danger,
        pre_allowed=pre_allowed,
        unattended_safe=(
            is_unattended_safe(str(command)) if kabuk else tool.effect in _UNATTENDED_EFFECTS
        ),
    )


async def _ask_and_remember(
    prompter: Prompter,
    request: ApprovalRequest,
    session_allowed: set[str],
) -> Decision:
    answer = await prompter.confirm(request)
    if answer is ApprovalAnswer.SESSION:
        # Yıkıcı işlemler hiçbir zaman oturum iznine dönüşmez. UI bu seçeneği
        # zaten göstermez; ikinci savunma hattı özel prompter'ları da kapsar.
        if request.danger is None:
            session_allowed.add(_scope(request))
        return Decision.ALLOW
    if answer is ApprovalAnswer.ONCE or answer is True:
        return Decision.ALLOW
    return Decision.DENIED


def _scope(request: ApprovalRequest) -> str:
    """Oturum izninin dar kapsamı: araç ya da aynı shell komutu."""
    if request.tool.name == "run_shell":
        return f"run_shell:{str(request.args.get('command', '')).strip()}"
    return request.tool.name
