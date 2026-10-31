"""Otomatik kip denetçisi — sorulacak çağrıyı küçük/hızlı modelle sınıflandır (P-011).

Claude Code auto mode: kurallar ve salt-okunur denetiminden sonra kalan eylem ayrı bir
sınıflandırıcıya sorulur. Fusion'da sıra şudur ve değişmez:

    deny / yıkıcı / ask kuralı / izin listesi   → denetçi HİÇ çağrılmaz (`approval.py`)
    kuralın sabit riski (sudo, | sh, env…)        → denetçi çağrılmaz, sorulur
    kuralın sorduğu kalan çağrı (ask_only, on)    → model "güvenli" derse SORULMAZ
    kuralın geçirdiği yazan kabuk komutu (yalnız on) → model "riskli" derse SORULUR

Model yalnız kullanıcının KENDİ mesajlarını ve eylemi görür; araç çıktısı verilmez
(istem enjeksiyonuna karşı). Sırlar gönderilmeden maskelenir. Model yok, zaman aşımı,
bozuk cevap → kurallı yedek: kuralın kararı geçerli (eski davranış). Üst üste
`AUTO_REVIEW_MODEL_FAILURE_LIMIT` hatadan sonra oturumun kalanında model çağrılmaz.
Alt ajanlar denetçiye girmez (`auto_review` devredilmez): niyetleri model yazımıdır.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import replace
from enum import Enum
from pathlib import Path
from typing import Protocol

from ...config.keys import detect
from ...config.models import Config
from ...config.readiness import is_usable
from ...core.auto_review import (
    AUTO_REVIEW_ARGS_CHARS,
    AUTO_REVIEW_INTENT_CHARS,
    AUTO_REVIEW_INTENT_MESSAGES,
    AUTO_REVIEW_SUMMARY_CHARS,
    AutoClassifierMode,
    ReviewOutcome,
    ReviewSource,
    ReviewVerdict,
)
from ...core.events import AutoModeFellBack, AutoReviewDecided, EventPublisher
from ...core.redaction import redact
from ...core.steering import steering_text
from ...core.tools import ToolContext, ToolEffect, ToolFamily, tool_family
from ...core.types import CompletionRequest, Message, ModelResult, ModelSpec
from ...providers.factory import build_provider
from ...tools.auto_policy import auto_risks, is_fixed_risk
from ...tools.delete_preview import delete_caution
from ...tools.script_chain import script_chain_risk
from .approval import ApprovalMode, ApprovalRequest
from .auto_guard import AutoReviewState

_LOG = logging.getLogger(__name__)
_PROMPT = Path(__file__).parent / "prompts" / "auto_classifier.md"
#: Denetçi rolünün adı (muhasebe ve olaylarda görünür).
CLASSIFIER_ROLE = "denetci"
#: Kurallı yedeğin gerekçeleri.
RULE_FALLBACK_REASON = "denetçi modeli kullanılamadı; kural geçerli: {reason}"
RULE_PASSED_REASON = "kurallar sorun görmedi"
#: Onay kartına eklenen not.
CARD_NOTE = "Denetçi: {reason}"
#: Kuralın geçirdiği ama denetçinin riskli bulduğu çağrının sorulma gerekçesi.
ESCALATED_RISK = "denetçi riskli buldu: {reason}"
#: Ayrı denetçi modeli seçilmediyse durum ekranındaki ad.
JUDGE_LABEL = "hakem ({model})"
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_SAFE_WORDS = frozenset({"guvenli", "safe", "allow"})
_RISKY_WORDS = frozenset({"riskli", "risky", "ask", "block", "deny"})


class ReviewKind(Enum):
    """Denetçinin bu çağrıda ne yapabileceği."""

    #: Kural soracak; model "güvenli" derse sorulmaz.
    RELAX = "relax"
    #: Kural geçirecek; model "riskli" derse sorulur (yalnız `on`).
    ESCALATE = "escalate"


class ReviewDeps(Protocol):
    """Denetçinin motordan okuduğu alanlar (`AgentDeps` bunları taşır)."""

    config: Config
    publisher: EventPublisher
    tool_context: ToolContext
    approval_mode: Callable[[], ApprovalMode] | None
    live_history: Callable[[], Sequence[Message]] | None
    auto_review: AutoReviewState | None


async def review_auto_request(request: ApprovalRequest, deps: ReviewDeps) -> ApprovalRequest:
    """Otomatik kipte isteği denetçiden geçir; kararla güncellenmiş isteği döndür.

    Denetçi kapalıysa, kip Otomatik değilse ya da çağrı denetçiye uygun değilse istek
    AYNEN döner (davranış eskisiyle birebir).
    """
    state = getattr(deps, "auto_review", None)
    if state is None or state.fell_back:
        # Denetçisiz çağıranlar (alt ajan, eski testlerin sade bağımlılıkları) aynen geçer.
        return request
    setting = getattr(deps.config.runtime, "auto_classifier", AutoClassifierMode.OFF)
    mode = getattr(deps, "approval_mode", None)
    if setting is AutoClassifierMode.OFF:
        return request
    if mode is None or mode() is not ApprovalMode.AUTO:
        return request
    root = deps.tool_context.root
    kind = review_kind(request, setting, root, tuple(deps.tool_context.touched))
    if kind is None or (state.remembered is not None and state.remembered(request)):
        return request
    intent = user_intent(getattr(deps, "live_history", None))
    key = _cache_key(request, intent)
    cached = state.cached(key)
    if cached is not None:
        outcome = replace(cached, source=ReviewSource.CACHE)
    else:
        outcome = await classify(
            request, intent, deps.config, deps.publisher, root=root, kind=kind, state=state
        )
        state.remember(key, outcome)
    trip = state.record(outcome)
    deps.publisher.publish(
        AutoReviewDecided(
            tool=outcome.tool,
            verdict=outcome.verdict,
            reason=outcome.reason,
            source=outcome.source,
            summary=outcome.summary,
            consecutive=state.consecutive,
            total=state.total,
        )
    )
    if trip is not None:
        deps.publisher.publish(AutoModeFellBack(reason=trip, trips=state.trips))
    return apply_outcome(request, outcome, kind)


def review_kind(
    request: ApprovalRequest,
    setting: AutoClassifierMode,
    root: Path | None,
    touched: Sequence[Path] = (),
) -> ReviewKind | None:
    """Çağrı denetçiye uygun mu, uygunsa hangi yönde? Uygun değilse None."""
    if (
        request.pre_denied is not None
        or request.danger is not None
        or request.pre_ask is not None
        or request.pre_allowed
        or request.effect in (ToolEffect.REMOTE_SESSION, ToolEffect.REMOTE_DESTRUCTIVE)
    ):
        return None
    command = request.args.get("command")
    is_shell = tool_family(request.tool.name) is ToolFamily.SHELL and isinstance(command, str)
    if request.risk is not None:
        if is_fixed_risk(request.risk):
            return None
        if is_shell and has_fixed_shell_risk(str(command), root, touched):
            return None
        return ReviewKind.RELAX
    if setting is AutoClassifierMode.ON and is_shell and not request.read_only:
        # Proje betiği (`python3 x.py`, `./build`) de kuralca serbesttir; içerik istem
        # enjeksiyonuyla yazılmış olabilir, bu yüzden `on` her yazan komuta bakar.
        return ReviewKind.ESCALATE
    return None


def has_fixed_shell_risk(command: str, root: Path | None, touched: Sequence[Path] = ()) -> bool:
    """Komutta (herhangi bir parçasında) denetçiye bırakılamayan bir risk var mı?

    `ApprovalRequest.risk` yalnız İLK gerekçeyi taşır; `git push && sudo …` zincirinde
    sudo gizlenmesin diye tüm gerekçeler ve silme/betik zinciri ayrıca denetlenir.
    """
    if any(is_fixed_risk(reason) for reason in auto_risks(command, root)):
        return True
    if root is None:
        return False
    return (
        delete_caution(command, root, Path.home()) is not None
        or script_chain_risk(command, root, touched) is not None
    )


def user_intent(history: Callable[[], Sequence[Message]] | None) -> tuple[str, ...]:
    """Kullanıcının son birkaç mesajı (kısaltılmış, sırları maskeli); yoksa boş.

    Harness notları (`harness_note`: iç içe proje talimatı, sıkıştırma özeti, refleksiyon
    notu) rolü `user` olsa da kullanıcının sözü değildir; yalnız araya girme yönergesi
    sayılır. Ölçüldü (31 Ekim): depodaki talimat dosyası "kullanıcının isteği" diye modele
    gidiyor, notlar son 3 mesajlık pencereyi doldurup asıl isteği dışarı itiyordu.
    """
    if history is None:
        return ()
    users = [text for text in map(_user_text, history()) if text is not None]
    return tuple(
        redact(text.strip()[:AUTO_REVIEW_INTENT_CHARS])
        for text in users[-AUTO_REVIEW_INTENT_MESSAGES:]
        if text.strip()
    )


def _user_text(message: Message) -> str | None:
    if message.role != "user":
        return None
    if message.harness_note:
        return steering_text(message)
    return message.content


async def classify(
    request: ApprovalRequest,
    intent: Sequence[str],
    config: Config,
    publisher: EventPublisher | None,
    *,
    root: Path | None,
    kind: ReviewKind,
    state: AutoReviewState | None = None,
) -> ReviewOutcome:
    """Modele sor; olmazsa kurallı yedeğin kararını döndür. Hiç istisna fırlatmaz."""
    summary = request_summary(request)
    if state is not None and state.model_unavailable:
        return _rule_outcome(request, summary, kind)
    if not is_usable(classifier_spec(config), detect()):
        # Anahtarsız kurulum: ağa hiç çıkılmaz, kurallar geçerli (ücretsiz/çevrimdışı yol).
        return _rule_outcome(request, summary, kind)
    prompt = build_prompt(request, intent, root)
    timeout = config.runtime.auto_classifier_timeout_s
    try:
        result = await asyncio.wait_for(_ask(prompt, config, publisher), timeout=timeout + 2.0)
    except TimeoutError:
        result = None
    except Exception:  # sınır: sağlayıcı kurulamadı/çöktü; denetçi bir hızlandırmadır
        _LOG.warning("Denetçi modeli çağrılamadı", exc_info=True)
        result = None
    parsed = parse_verdict(result.text) if result is not None and result.ok else None
    if parsed is None:
        if state is not None:
            state.note_model_failure()
        return _rule_outcome(request, summary, kind)
    if state is not None:
        state.note_model_success()
    verdict, reason = parsed
    return ReviewOutcome(request.tool.name, verdict, reason, ReviewSource.MODEL, summary)


def apply_outcome(
    request: ApprovalRequest, outcome: ReviewOutcome, kind: ReviewKind
) -> ApprovalRequest:
    """Kararı isteğe işle: güvenli + RELAX → sorulmaz; riskli + ESCALATE → sorulur."""
    if outcome.source is ReviewSource.RULE:
        return request
    note = CARD_NOTE.format(reason=outcome.reason)
    if kind is ReviewKind.RELAX:
        if outcome.verdict is ReviewVerdict.SAFE:
            return replace(request, risk=None, note=note)
        return replace(request, note=f"{request.note}. {note}" if request.note else note)
    if outcome.verdict is ReviewVerdict.RISKY:
        risk = ESCALATED_RISK.format(reason=outcome.reason)
        return replace(request, risk=risk, note=risk, unattended_safe=False)
    return request


def build_prompt(request: ApprovalRequest, intent: Sequence[str], root: Path | None) -> str:
    """Denetçi istemi: talimat + kullanıcı mesajları + eylem (sırlar maskeli)."""
    args = json.dumps(dict(request.args), ensure_ascii=False, default=str)
    lines = [
        _PROMPT.read_text(encoding="utf-8").strip(),
        "",
        "## Kullanıcının mesajları (eskiden yeniye)",
        *(f"- {text}" for text in intent),
        *(("- (mesaj yok)",) if not intent else ()),
        "",
        "## Eylem",
        f"Proje kökü: {root if root is not None else '(bilinmiyor)'}",
        f"Araç: {request.tool.name}",
        f"Argümanlar: {redact(args[:AUTO_REVIEW_ARGS_CHARS])}",
        f"Kuralın notu: {request.risk or RULE_PASSED_REASON}",
    ]
    return "\n".join(lines)


def parse_verdict(text: str) -> tuple[ReviewVerdict, str] | None:
    """Model cevabından kararı çıkar; tanınmazsa None (kurallı yedek devreye girer)."""
    match = _JSON_OBJECT.search(text or "")
    if match is None:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    raw = _fold(str(payload.get("karar", "")))
    reason = str(payload.get("gerekce", "")).strip()[:AUTO_REVIEW_SUMMARY_CHARS] or "gerekçe yok"
    if raw in _SAFE_WORDS:
        return ReviewVerdict.SAFE, reason
    if raw in _RISKY_WORDS:
        return ReviewVerdict.RISKY, reason
    return None


def _fold(text: str) -> str:
    """Büyük/küçük harf ve Türkçe işaretten bağımsız biçim: `GÜVENLİ` → `guvenli`."""
    decomposed = unicodedata.normalize("NFKD", text.strip())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return plain.lower().replace("ı", "i")


def request_summary(request: ApprovalRequest) -> str:
    """Kart/olay için kısa hedef: komut, yol ya da araç adı."""
    target = request.args.get("command") or request.args.get("path") or request.tool.name
    text = redact(" ".join(str(target).split()))
    if len(text) > AUTO_REVIEW_SUMMARY_CHARS:
        return text[: AUTO_REVIEW_SUMMARY_CHARS - 1] + "…"
    return text


def classifier_spec(config: Config) -> ModelSpec:
    """Denetçi modeli: `auto_classifier_model` ya da hakem rolü (yedekleriyle)."""
    chosen = config.runtime.auto_classifier_model.strip()
    if chosen:
        return ModelSpec(name=CLASSIFIER_ROLE, model=chosen)
    return replace(config.judge, name=CLASSIFIER_ROLE)


def classifier_label(config: Config) -> str:
    """Durum ekranında görünen denetçi modeli: açık seçim ya da `hakem (<model>)`."""
    chosen = config.runtime.auto_classifier_model.strip()
    return chosen or JUDGE_LABEL.format(model=config.judge.model)


def _rule_outcome(request: ApprovalRequest, summary: str, kind: ReviewKind) -> ReviewOutcome:
    if kind is ReviewKind.RELAX:
        reason = RULE_FALLBACK_REASON.format(reason=request.risk or "")
        return ReviewOutcome(
            request.tool.name, ReviewVerdict.RISKY, reason, ReviewSource.RULE, summary
        )
    return ReviewOutcome(
        request.tool.name, ReviewVerdict.SAFE, RULE_PASSED_REASON, ReviewSource.RULE, summary
    )


def _cache_key(request: ApprovalRequest, intent: Sequence[str]) -> str:
    identity = [request.tool.name, dict(request.args), request.risk, list(intent)]
    return hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


async def _ask(prompt: str, config: Config, publisher: EventPublisher | None) -> ModelResult:
    request = CompletionRequest(
        messages=(Message("user", prompt),),
        temperature=config.runtime.judge_temperature,
        max_tokens=config.runtime.judge_max_tokens,
        timeout_s=config.runtime.auto_classifier_timeout_s,
        disable_thinking=True,
    )
    # Arka plan çağrısı: ilerleme satırı yok, token muhasebeye girer. Yeniden deneme yok:
    # denetçi beklenirse kullanıcı da bekler; başarısızlık kurallı yedeğe düşer. Web
    # oturumu bağlanmaz (tarayıcı sohbeti her komutta açılmamalı).
    provider = build_provider(
        classifier_spec(config), publisher=publisher, retry_delays_s=(), background=True
    )
    return await provider.complete(request)
