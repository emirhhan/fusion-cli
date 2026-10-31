"""PR oluşturma/yorum beyanlarının kanıt kapısı ve oturum PR bağı (P-057).

Fusion'da PR, model + `run_shell` + onay yoluyla `gh pr create` ile açılır (başlık ve gövde
model işidir; deterministik bir iş akışı bunları üretemez). Bu modül iki şeyi kanıta bağlar:

- **Beyan kapısı:** cevap BİRİNCİ AĞIZDAN "PR'ı açtım / I opened a pull request" diyorsa,
  konuşmada başarılı bir PR oluşturma kanıtı (çıktısında PR adresi olan `gh pr create`,
  `gh api …/pulls` POST ya da MCP `create_pull_request`) OLMALI. Yoksa cevaba "kanıt yok"
  notu düşer (kullanıcı açılmamış bir PR'ı açılmış sanmasın). Yorum beyanı da aynı.
- **Oturum bağı:** turda açılan PR, yoksa geçerli depoda `gh pr view` ile okunan PR'ın
  kendi `url:` satırı oturumun PR künyesi olur (`core.pull_request.PullRequestLink`).

Ölçüldü (31 Ekim, bağımsız inceleme): (1) masaüstü tur sonu bağı `tool_uses` öğelerinin
`ToolUse` olduğunu varsayıp sahte sonuçta `AttributeError` ile turu düşürüyordu; (2) okuma
bağı çıktıdaki SON PR adresini alıyordu — başka depodaki PR ya da gövdedeki "Fixes …/pull/3"
oturumu yanlış PR'a bağlıyordu; (3) kapı yalnız `run_shell` + `gh pr create`'i kanıt sayıyor,
"PR #5 zaten açıldı", "The PR was created by Alice" gibi üçüncü kişi cümlelerinde ve önceki
turda açılmış PR için "evet açtım" cevabında yanlış uyarı veriyordu.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING

from ...core.evidence import ToolUse
from ...core.pull_request import PullRequestLink, pr_links_in

if TYPE_CHECKING:
    from ...core.types import Message
    from ..agent.loop import AgentOutcome

_CMD_START = r"(?:^|[;&|(]\s*|\s)"
_GH_PR = re.compile(_CMD_START + r"gh\s+pr\s+(create|comment|review|view|checks|status)\b")
#: `gh api repos/o/r/pulls -f title=…` (alanlı ya da POST) → PR oluşturma.
_GH_API = re.compile(_CMD_START + r"gh\s+api\s+(?P<rest>[^;&|]*)")
_API_PULLS = re.compile(r"(?:^|\s|/)repos/[^\s/]+/[^\s/]+/pulls/?(?:\s|$)")
_API_COMMENTS = re.compile(r"/(?:issues|pulls)/\d+/(?:comments|reviews)\b")
_API_WRITE = re.compile(
    r"(?:^|\s)(?:-X\s*POST|--method[=\s]+POST|-f|-F|--field|--raw-field)\b", re.I
)
#: GitHub MCP sunucusunun araçları (`<sunucu>__<araç>` biçiminde kayıtlı).
_MCP_CREATE = re.compile(r"(?:^|__)create_pull_request$")
_MCP_COMMENT = re.compile(
    r"(?:^|__)(?:add_issue_comment|add_comment_to_pending_review|"
    r"create_and_submit_pull_request_review|submit_pending_pull_request_review|"
    r"add_pull_request_review_comment\w*)$"
)
#: Başka depoyu hedefleyen okuma oturumu bağlamaz.
_OTHER_REPO = re.compile(r"(?:^|\s)(?:--repo|-R)(?:[=\s]|$)")
#: `gh pr view` düz çıktısının `url:` satırı ya da `--json url` alanı: PR'ın KENDİ adresi.
_OWN_URL = re.compile(r'^\s*url:\s*(\S+)|"url"\s*:\s*"([^"]+)"', re.MULTILINE)

_PR_WORD = r"\b(?:pr|pull request|çekme isteği|cekme istegi)"
#: Birinci ağızdan oluşturma: "PR'ı açtım", "pull request oluşturduk", "I opened a PR".
_CREATE_FIRST_PERSON = re.compile(
    _PR_WORD + r"[^.!?\n]{0,60}?\b(?:açtım|actim|açtık|actik|oluşturdum|olusturdum|"
    r"oluşturduk|olusturduk)\b|"
    r"\b(?:I|we)(?:'ve| have)?\s+(?:just\s+|now\s+)?(?:opened|created|submitted|raised)\s+"
    r"(?:a\s+|the\s+|an?\s+new\s+|new\s+)?(?:pr|pull request)\b",
    re.IGNORECASE,
)
#: Türkçe edilgen ("PR açıldı: …") Fusion cevaplarında birinci ağız yerine sık kullanılır;
#: üçüncü kişi/önceki iş belirteci içeren cümlede beyan sayılmaz.
_CREATE_PASSIVE = re.compile(
    _PR_WORD + r"[^.!?\n]{0,60}?\b(?:açıldı|acildi|oluşturuldu|olusturuldu)\b", re.IGNORECASE
)
_THIRD_PARTY = re.compile(
    r"\b(?:zaten|daha önce|önceden|önceki|tarafından|already|by|bot)\b", re.IGNORECASE
)
_COMMENT_CLAIM = re.compile(
    _PR_WORD + r"[^.!?\n]{0,60}?\byorum (?:yazdım|ekledim|bıraktım|biraktim|gönderdim)\b|"
    r"\b(?:I|we)(?:'ve| have)?\s+(?:just\s+)?(?:commented on|reviewed)\s+(?:the\s+)?"
    r"(?:pr|pull request)\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"[^.!?\n]+")

UNVERIFIED_CREATE = (
    "Not: Bu konuşmada başarılı bir PR oluşturma çıktısı (PR adresi) görülmedi; PR açılmamış "
    "olabilir. `gh pr status` ile doğrula ya da `/pr` ile yeniden dene."
)
UNVERIFIED_COMMENT = (
    "Not: Bu konuşmada başarılı bir PR yorumu kanıtı görülmedi; yorum gönderilmemiş olabilir."
)


def _tool_uses(items: Sequence[object]) -> Iterator[ToolUse]:
    """Yalnız gerçek `ToolUse` öğeleri: sahte/eski sonuçlar (`("mutating",)`) atlanır."""
    return (item for item in items if isinstance(item, ToolUse))


def _shell_action(command: str) -> str | None:
    match = _GH_PR.search(command)
    if match:
        action = match.group(1)
        return "comment" if action == "review" else action
    api = _GH_API.search(command)
    if api is None or not _API_WRITE.search(" " + api.group("rest")):
        return None
    rest = api.group("rest")
    if _API_COMMENTS.search(rest):
        return "comment"
    return "create" if _API_PULLS.search(" " + rest) else None


def _action(use: ToolUse) -> str | None:
    if use.name == "run_shell":
        return _shell_action(str(use.arguments.get("command", "")))
    if use.name == "gh":
        # Salt-okur `gh` aracı (`tools/github_cli.py`): yalnız okuma eylemleri.
        match = re.match(r"\s*pr\s+(view|checks|status)\b", str(use.arguments.get("args") or ""))
        return match.group(1) if match else None
    if _MCP_CREATE.search(use.name):
        return "create"
    if _MCP_COMMENT.search(use.name):
        return "comment"
    return None


def _target_text(use: ToolUse) -> str:
    return str(use.arguments.get("command") or use.arguments.get("args") or "")


def created_pull_requests(tool_uses: Sequence[object]) -> tuple[PullRequestLink, ...]:
    """Başarılı PR oluşturma çıktılarındaki PR'lar (`gh pr create`, `gh api`, MCP)."""
    links: list[PullRequestLink] = []
    for use in _tool_uses(tool_uses):
        if use.ok and _action(use) == "create":
            found = pr_links_in(use.output)
            # `gh pr create` adresi son satıra yazar; JSON yanıtta ilk `html_url` PR'ın kendisi.
            if found:
                links.append(found[-1] if use.name == "run_shell" else found[0])
    return tuple(dict.fromkeys(links))


def _read_pull_request(use: ToolUse) -> PullRequestLink | None:
    """`gh pr view` çıktısındaki PR'ın KENDİ adresi; başka depo hedefliyse None."""
    if not use.ok or _action(use) != "view" or _OTHER_REPO.search(" " + _target_text(use)):
        return None
    for match in _OWN_URL.finditer(use.output):
        links = pr_links_in(match.group(1) or match.group(2) or "")
        if links:
            return links[0]
    return None


def session_pull_request(tool_uses: Sequence[object]) -> PullRequestLink | None:
    """Oturumun bağlanacağı PR: son açılan, yoksa geçerli depoda son okunan; yoksa None."""
    created = created_pull_requests(tool_uses)
    if created:
        return created[-1]
    read = [link for use in _tool_uses(tool_uses) if (link := _read_pull_request(use))]
    return read[-1] if read else None


def tool_uses_from_messages(messages: Sequence[Message]) -> tuple[ToolUse, ...]:
    """Konuşma geçmişindeki araç çağrıları (çağrı + sonucu eşlenir); önceki turların kanıtı."""
    calls = {call.id: call for message in messages for call in message.tool_calls}
    uses: list[ToolUse] = []
    for message in messages:
        call = calls.get(message.tool_call_id or "") if message.role == "tool" else None
        if call is None:
            continue
        try:
            arguments = json.loads(call.arguments or "{}")
        except ValueError:
            arguments = {}
        uses.append(
            ToolUse(
                name=call.name,
                ok=message.ok is not False,
                arguments=arguments if isinstance(arguments, dict) else {},
                output=message.content,
            )
        )
    return tuple(uses)


def _claims_creation(text: str) -> bool:
    if _CREATE_FIRST_PERSON.search(text):
        return True
    return any(
        _CREATE_PASSIVE.search(sentence) and not _THIRD_PARTY.search(sentence)
        for sentence in _SENTENCE.findall(text)
    )


def unverified_pr_notes(
    text: str, tool_uses: Sequence[object], history: Sequence[Message] = ()
) -> tuple[str, ...]:
    """Kanıtsız PR beyanları için kullanıcı notları (beyan yoksa boş).

    Kanıt bu turun araçlarından ya da konuşmanın önceki turlarından gelebilir: önceki turda
    açılmış PR için "evet, açtım" cevabı uyarı almaz.
    """
    creates = _claims_creation(text)
    comments = bool(_COMMENT_CLAIM.search(text))
    if not creates and not comments:
        return ()
    evidence = (*_tool_uses(tool_uses), *tool_uses_from_messages(history))
    notes: list[str] = []
    if creates and not created_pull_requests(evidence):
        notes.append(UNVERIFIED_CREATE)
    if comments and not any(use.ok and _action(use) == "comment" for use in evidence):
        notes.append(UNVERIFIED_COMMENT)
    return tuple(notes)


def disclose_unverified_pr(outcome: AgentOutcome) -> None:
    """Kanıtsız PR beyanı varsa cevabın sonuna not ekle (yerinde; tur sonucu)."""
    notes = [
        note
        for note in unverified_pr_notes(outcome.final_text, outcome.tool_uses, outcome.messages)
        if note not in outcome.final_text
    ]
    if notes:
        outcome.final_text = outcome.final_text.rstrip() + "\n\n" + "\n".join(notes)
