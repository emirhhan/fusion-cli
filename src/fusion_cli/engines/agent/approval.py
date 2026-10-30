"""Onay politikaları — "bu değişikliğe izin var mı?" sorusunun tek cevap yeri.

Beş kip tek bir protokolün arkasındadır (Claude'un izin kipleriyle aynı adlar);
motor hangi kipte olduğunu bilmez, yalnızca `decide` çağırır.

    auto      Fusion karar verir: projede iş gören her şey sorulmadan yapılır;
              yalnız riskli olan (proje dışı, sistem, yayın/push, uzak sunucu,
              dikkat gerektiren silme, uzak sistemde değişiklik) sorulur
    edits     dosya düzenlemeleri ve tanınan güvenli komutlar sorulmaz; kalan sorulur
    security  "Manuel": okuma dışındaki her işlem tek tek sorulur
    plan      hiçbir değişikliğe izin yok; yalnız okuma, keşif ve plan
    bypass    hiçbir şey sorulmaz (silinen yine Fusion çöpüne gider); tek istisna:
              uzak sistemde geri alınamaz etki bildiren araç her çağrıda sorulur

Yıkıcı komut (`danger`) auto, edits ve security kiplerinde DAİMA sorulur ve oturum
iznine dönüşmez: otomatik onay hız içindir, geri alınamaz bir işlemi sessizce
yapmak için değil. Sade `rm` yıkıcı sayılmaz — çöpe gider ve geri alınır.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from ...config.permissions import is_allowed
from ...core.tools import (
    AuthorizationScope,
    Tool,
    ToolArgs,
    ToolContext,
    ToolEffect,
    ToolFamily,
    tool_family,
)
from ...tools.auto_policy import auto_risk, is_read_only_command
from ...tools.command_policy import is_unattended_safe
from ...tools.delete_preview import delete_caution, describe_delete, script_danger
from ...tools.safe_delete import simple_rm_targets
from ...tools.safety import TRASHABLE_DELETE_REASONS, danger_reason
from ...tools.script_chain import script_chain_risk

#: Uzak sistemde geri alınamaz değişiklik yapabilen aracın onay gerekçesi.
REMOTE_DESTRUCTIVE_REASON = (
    "Bu uzak araç kendini geri alınamaz değişiklik yapabilir olarak tanımlıyor "
    "(silme, yayınlama veya harcama). Her çağrıda ayrıca onay istenir."
)

#: Uzak sistemde değişiklik yapan aracın otomatik kipte sorulma gerekçesi.
REMOTE_WRITE_REASON = "uzak sistemde değişiklik yapıyor"

#: Hedef yolu `path` argümanında taşıyan yerel dosya yazma araçları (A1-06).
_PATH_WRITE_TOOLS = frozenset({"write_file", "edit_file", "multi_edit", "create_file"})

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


#: Shift+Tab döngüsü (Claude'daki sıra). "İzinleri atla" BİLEREK yok: tek tuşla
#: yanlışlıkla açılmamalı; `/bypass` ile açıkça seçilir.
CYCLE_MODES = (
    ApprovalMode.AUTO,
    ApprovalMode.SECURITY,
    ApprovalMode.ACCEPT_EDITS,
    ApprovalMode.PLAN,
)


def next_mode(mode: ApprovalMode) -> ApprovalMode:
    """Döngüdeki sıradaki kip; döngü dışındaki kipten (bypass) Otomatik'e dönülür."""
    if mode not in CYCLE_MODES:
        return ApprovalMode.AUTO
    return CYCLE_MODES[(CYCLE_MODES.index(mode) + 1) % len(CYCLE_MODES)]


#: Kipin elle yazılabilen öteki adları (Claude'daki adlar dahil).
_MODE_ALIASES = {
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
    #: Kimseye SORULAMADI (oturum etkileşimsiz — TTY yok, boru hattı, CI).
    #:
    #: Kullanıcının gerçekten "hayır" demesiyle (`DENY`) KARIŞTIRILMAMALI: ikisi
    #: `Decision`de de ayrı sonuçlara gider (`_ask_and_remember`). Reddeden bir
    #: insan turu durdurur; sorulamayan bir oturum turu SÜRDÜRÜR ve modele başka
    #: bir yol denemesi söylenir.
    UNAVAILABLE = "unavailable"


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

    @property
    def can_remember(self) -> bool:
        """Yalnız doğrulanmış dar kapsam oturum boyunca saklanır."""
        return self.danger is None and _scope(self) is not None

    @property
    def remembered_scope_description(self) -> str | None:
        """Uzak oturum iznini tüm arayüzlerde aynı açık kapsamla anlat."""
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

    async def confirm(self, request: ApprovalRequest) -> bool | ApprovalAnswer: ...


class ApprovalPolicy(Protocol):
    """Bir araç çağrısına izin verilip verilmeyeceğine karar verir."""

    async def decide(self, request: ApprovalRequest) -> Decision: ...


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

    async def decide(self, request: ApprovalRequest) -> Decision:
        if request.danger is None and (request.pre_allowed or self._allows(request)):
            return Decision.ALLOW
        if self._memory.is_remembered(request):
            return Decision.ALLOW
        return await _ask_and_remember(self._prompter, request, self._memory)


class AutoApproval(_AskingApproval):
    """Otomatik: Fusion karar verir, yalnız RİSKLİ olanı sorar (`auto_policy`).

    Eskiden beyaz listeye bakıyordu ve `php -l`, `lsof`, `unzip` gibi sıradan
    komutlarda bile soruyordu; kullanıcı (2 Ekim) "gereksiz yerlerde soru
    soruyor, sormasın" dedi. Beyaz liste artık "Düzenlemeleri kabul et" kipidir.
    """

    def _allows(self, request: ApprovalRequest) -> bool:
        return request.risk is None


class AcceptEditsApproval(_AskingApproval):
    """Düzenlemeleri kabul et: dosya düzenlemeleri ve tanınan güvenli komutlar serbest."""

    def _allows(self, request: ApprovalRequest) -> bool:
        return request.unattended_safe


class SecurityApproval(_AskingApproval):
    """Manuel: okuma dışındaki her işlem tek tek sorulur.

    İstisna: kullanıcının kendi izin listesine yazdığı komutlar sorulmaz — kullanıcı
    o kararı zaten vermiştir. Yıkıcı komutlar bu istisnadan yararlanamaz.
    """

    def _allows(self, request: ApprovalRequest) -> bool:
        return request.read_only


class PlanApproval:
    """Plan modu: hiçbir değişikliğe izin verilmez, kullanıcıya da sorulmaz.

    Okumaya izin verilir — `ls`, `grep`, `git log` gibi salt okuyan kabuk komutu ve
    uzak sistemi YALNIZ okuyan çağrı (ör. mağazada ürün aramak). Claude'un plan
    kipi de okumaya izin verir; plan gerçek veriye dayanmalıdır. Eskiden kabuk
    tamamen kapalıydı ve model plan için `git log` bile çalıştıramıyordu.
    """

    async def decide(self, request: ApprovalRequest) -> Decision:
        if request.read_only and request.danger is None:
            return Decision.ALLOW
        return Decision.BLOCKED


class BypassApproval:
    """İzinleri atla: neredeyse hiçbir şey sorulmaz. Sade `rm` yine çöpe gider (`shell`).

    TEK sert tavan (A1-08): uzak sistemde GERİ ALINAMAZ etki bildiren araç
    (`REMOTE_DESTRUCTIVE`: silme, yayınlama, harcama) bypass'ta bile her çağrıda son
    kez sorulur ve oturum iznine dönüşmez. Yerel komutlar (git push, sudo vb.)
    kullanıcının bilinçli seçimi olarak serbest kalır.
    """

    def __init__(
        self, prompter: Prompter | None = None, memory: ApprovalMemory | None = None
    ) -> None:
        self._prompter = prompter
        self._memory = memory if memory is not None else ApprovalMemory()

    async def decide(self, request: ApprovalRequest) -> Decision:
        if request.effect is not ToolEffect.REMOTE_DESTRUCTIVE or self._prompter is None:
            return Decision.ALLOW
        return await _ask_and_remember(self._prompter, request, self._memory)


def build_policy(
    mode: ApprovalMode, prompter: Prompter, memory: ApprovalMemory | None = None
) -> ApprovalPolicy:
    """Moda karşılık gelen politikayı üret.

    `memory` verilmezse tek turluk taze hafıza kurulur; sohbet boyunca yaşayan
    çağıranlar kendi hafızalarını her turda aynı nesneyle geçirir.
    """
    if mode is ApprovalMode.PLAN:
        return PlanApproval()
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
) -> ApprovalRequest:
    """Onay isteğini, araç çağrı bazlı etki bildiriyorsa o etkiyle kur.

    Çözücü `None` dönerse ya da yoksa aracın kendi etkisi geçerlidir.
    """
    effect = await tool.effect_resolver(args, context) if tool.effect_resolver is not None else None
    touched = context.touched if context is not None else ()
    extra_roots = tuple(context.extra_roots) if context is not None else ()
    return build_request(
        tool,
        args,
        allowed_commands,
        effect=effect,
        root=root,
        touched=touched,
        extra_roots=extra_roots,
    )


def build_request(
    tool: Tool,
    args: ToolArgs,
    allowed_commands: frozenset[str] = frozenset(),
    *,
    effect: ToolEffect | None = None,
    root: Path | None = None,
    touched: Collection[Path] = (),
    extra_roots: tuple[Path, ...] = (),
) -> ApprovalRequest:
    """Onay isteğini kur; yıkıcılık, risk ve izin listesi kontrolü burada yapılır.

    Uzak araçlar kabuk komutu gibi ele alınır: bir reklam MCP'sinin bütçe değiştiren
    aracı (REMOTE_WRITE) otomatik kipte sorulur; okuyan ve sayfayla etkileşen araç
    sorulmaz.
    """
    command = args.get("command")
    # Sınıflandırma TEK KAYNAKTAN (`core.tools.tool_family`) okunur: birebir ad
    # karşılaştırması `bash`/`shell`/`execute_command` takma adıyla çağrılan bir
    # kabuk komutunu kaçırır ve onun güvenlik/izin-listesi denetimini atlardı.
    effect = effect or tool.effect
    if tool_family(tool.name) is ToolFamily.SHELL and isinstance(command, str):
        return _shell_request(tool, args, command, allowed_commands, effect, root, touched)
    danger = danger_reason(tool.name, args)
    if danger is None and effect is ToolEffect.REMOTE_DESTRUCTIVE:
        danger = REMOTE_DESTRUCTIVE_REASON
    risk = None if effect in _UNATTENDED_EFFECTS else REMOTE_WRITE_REASON
    unattended_safe = effect in _UNATTENDED_EFFECTS
    # Yerel dosya aracı proje DIŞINA yazıyorsa risklidir (modül belgesi: "proje dışı
    # sorulur"). Eskiden bu yalnız kabukta uygulanıyordu; `write_file ~/.zshrc`
    # auto kipte sorulmuyor, "oturum boyunca" izni de araç adına bağlı olduğundan
    # sonraki her yolu kapsıyordu. Ölçüldü (29 Ekim, A1-06).
    outside_dir = _outside_write_dir(tool, args, root, extra_roots) if risk is None else None
    if outside_dir is not None:
        risk = f"proje dışına yazıyor ({args.get('path')})"
        unattended_safe = False
    return ApprovalRequest(
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
    )


def _outside_write_dir(
    tool: Tool, args: ToolArgs, root: Path | None, extra_roots: tuple[Path, ...]
) -> str | None:
    """Dosya yazma aracının hedefi kök (+ `--add-dir`) dışındaysa hedefin dizini."""
    raw = args.get("path")
    if root is None or tool.name not in _PATH_WRITE_TOOLS or not isinstance(raw, str):
        return None
    if not raw.strip():
        return None
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
) -> ApprovalRequest:
    """Kabuk komutunun onay isteği: kart komutu değil SONUCU göstermeli."""
    danger = danger_reason(tool.name, args)
    trashed = simple_rm_targets(command) is not None
    if trashed and danger in TRASHABLE_DELETE_REASONS:
        # Sade `rm` kalıcı silmez, Fusion çöpüne taşır (`shell._guarded_delete`).
        danger = None
    home = Path.home()
    if danger is None and root is not None:
        danger = script_danger(command, root, home)
    caution = delete_caution(command, root, home) if root is not None else None
    target = describe_delete(command, root, home) if root is not None else ""
    chain = script_chain_risk(command, root, touched)
    risk = caution or auto_risk(command, root) or chain
    if danger is not None and target:
        danger = f"{danger}. {target}"
    note = ". ".join(part for part in (risk, target) if part) or None
    return ApprovalRequest(
        tool=tool,
        args=args,
        danger=danger,
        pre_allowed=is_allowed(command, allowed_commands),
        unattended_safe=(trashed and caution is None)
        or (chain is None and is_unattended_safe(command, root)),
        effect=effect,
        risk=risk,
        read_only=is_read_only_command(command),
        note=note,
    )


async def _ask_and_remember(
    prompter: Prompter,
    request: ApprovalRequest,
    memory: ApprovalMemory,
) -> Decision:
    revision = memory.revision
    answer = await prompter.confirm(request)
    if memory.revision != revision:
        return Decision.BLOCKED
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
