"""`/team` komutu (P-061): ajan ekiplerini listele, panoyu göster, ekip kur ya da sürdür.

    /team                          ekipler ve görev ilerlemesi
    /team goster <ad>              pano: görevler, üyeler, lidere gelen son mesajlar
    /team sil <ad>                 panoyu ve gelen kutularını sil
    /team mesaj <ad> <üye> <metin> ekibi sürdür, üyeye mesaj ilet
    /team [kur] <hedef>            lider (ana ajan) ekibi kursun ve çalıştırsın

Alt komut yalnız biçimi tutunca çalışır (`liste` tek başına; `goster`/`sil` tek adla;
`mesaj` kayıtlı ekip adı ister, yoksa `kur` ipucu verir); "sil eski logları temizle"
gibi cümle hedef sayılır. Ölçüldü
(31 Ekim): ilk kelime her durumda alt komut sayılıyor, "list the open PRs" ekip listesi,
"sil eski loglari temizle" "adlı ekip yok" dönüyordu.

Kurma/sürdürme bir ajan turu hazırlar (`pending_task`); masaüstü aynı komutu çalıştırır.
Metin Rich işaretlemesi taşımaz (REPL sonucu işaretlemeli basar).
"""

from __future__ import annotations

from ...engines.agent.team_board import LEAD, NAME_PATTERN, TeamError, TeamStore
from ...engines.agent.team_tools_member import render_board
from .state import Engine, ReplState

#: `goster`te lidere gelen son mesaj sayısı.
LEAD_MESSAGES = 10

USAGE = (
    "Kullanım: /team [goster <ad>] | sil <ad> | mesaj <ad> <üye> <metin> | [kur] <hedef>\n"
    "Panolar: .fusion/ekip/<ad>/ (görev listesi + gelen kutuları)."
)
BUILD_HINT = " Bu bir hedefse: /team kur <hedef>"
NONE_SAVED = "Henüz ekip yok. '/team <hedef>' ile lider bir ekip kursun."
BUILD_TASK = (
    "Bu iş için bir ajan EKİBİ kur ve team_run aracıyla çalıştır. Hedef: {goal}\n"
    "Üyeleri (ad, uzman, yazma alanı ya da salt okur) ve görevleri bağımlılıklarıyla sen "
    "belirle; birbirinin dosyasına yazmasınlar. Bitince ekip raporunu kısaca özetle."
)
MESSAGE_TASK = (
    "team_run aracıyla '{team}' ekibini sürdür (ad: \"{team}\") ve {member} üyesine şu "
    "mesajı ilet: {text}\nBitince ekip raporunu kısaca özetle."
)


_LIST = frozenset({"liste", "list"})
_SHOW = frozenset({"goster", "göster", "show"})
_DELETE = frozenset({"sil", "delete"})
_MESSAGE = frozenset({"mesaj", "message"})
_BUILD = frozenset({"kur", "build"})


def team_command(state: ReplState, argument: str) -> str:
    store = TeamStore(state.root)
    text = argument.strip()
    word, _, rest = text.partition(" ")
    action, rest = word.casefold(), rest.strip()
    if not text or (action in _LIST and not rest):
        return overview(store)
    if action in _BUILD:
        return _build(state, rest) if rest else USAGE
    if action in _SHOW | _DELETE and rest and " " not in rest:
        if rest not in store.names():
            # Tek kelimelik geçerli ad: büyük olasılıkla yanlış yazılmış ekip adı.
            if NAME_PATTERN.match(rest):
                return f"'{rest}' adlı ekip yok.{BUILD_HINT}\n\n{overview(store)}"
            return _build(state, text)
        if action in _SHOW:
            return show(store, rest)
        return f"Silindi: {rest}" if store.delete(rest) else f"'{rest}' adlı ekip yok."
    if action in _MESSAGE:
        parts = rest.split(" ", 2)
        if len(parts) < 3 or not parts[2].strip():
            return USAGE
        team, member, message = parts
        if team not in store.names():
            return f"'{team}' adlı ekip yok.{BUILD_HINT}\n\n{overview(store)}"
        state.engine = Engine.AGENT
        state.pending_task = MESSAGE_TASK.format(team=team, member=member, text=message.strip())
        return f"'{team}' ekibi sürdürülüyor…"
    return _build(state, text)


def _build(state: ReplState, goal: str) -> str:
    state.engine = Engine.AGENT
    state.pending_task = BUILD_TASK.format(goal=goal)
    return "Lider ekibi kuruyor…"


def overview(store: TeamStore) -> str:
    names = store.names()
    if not names:
        return NONE_SAVED
    lines = ["Ekipler:"]
    for name in names:
        try:
            board = store.load(name)
        except TeamError as error:
            lines.append(f"  {name}  okunamadı: {error}")
            continue
        if board is None:
            continue
        done = sum(task.status == "tamam" for task in board.tasks)
        members = ", ".join(member.name for member in board.members)
        lines.append(
            f"  {name}  {done}/{len(board.tasks)} görev · üyeler: {members} — {board.goal}"
        )
    return "\n".join(lines)


def show(store: TeamStore, name: str) -> str:
    try:
        board = store.load(name)
    except TeamError as error:
        return str(error)
    if board is None:
        return f"'{name}' adlı ekip yok."
    text = render_board(board, viewer="")
    mail = store.inbox(name, LEAD)[-LEAD_MESSAGES:]
    if mail:
        text += "\n\nLidere gelen son mesajlar:\n" + "\n".join(
            f"- {message.sender}: {message.text}" for message in mail
        )
    return text
