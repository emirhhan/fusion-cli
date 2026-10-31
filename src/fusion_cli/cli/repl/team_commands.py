"""`/team` komutu (P-061): ajan ekiplerini listele, panoyu göster, ekip kur ya da sürdür.

    /team                          ekipler ve görev ilerlemesi
    /team goster <ad>              pano: görevler, üyeler, lidere gelen son mesajlar
    /team sil <ad>                 panoyu ve gelen kutularını sil
    /team mesaj <ad> <üye> <metin> ekibi sürdür, üyeye mesaj ilet
    /team <hedef>                  lider (ana ajan) ekibi kursun ve çalıştırsın

Kurma/sürdürme bir ajan turu hazırlar (`pending_task`); masaüstü aynı komutu çalıştırır.
Metin Rich işaretlemesi taşımaz (REPL sonucu işaretlemeli basar).
"""

from __future__ import annotations

from ...engines.agent.team_board import LEAD, TeamError, TeamStore
from ...engines.agent.team_tools_member import render_board
from .state import Engine, ReplState

#: `goster`te lidere gelen son mesaj sayısı.
LEAD_MESSAGES = 10

USAGE = (
    "Kullanım: /team [goster <ad>] | sil <ad> | mesaj <ad> <üye> <metin> | <hedef>\n"
    "Panolar: .fusion/ekip/<ad>/ (görev listesi + gelen kutuları)."
)
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


def team_command(state: ReplState, argument: str) -> str:
    store = TeamStore(state.root)
    word, _, rest = argument.strip().partition(" ")
    action = word.casefold()
    if not action or action in {"liste", "list"}:
        return overview(store)
    if action in {"goster", "göster", "show"}:
        return show(store, rest.strip()) if rest.strip() else USAGE
    if action in {"sil", "delete"}:
        name = rest.strip()
        if not name:
            return USAGE
        return f"Silindi: {name}" if store.delete(name) else f"'{name}' adlı ekip yok."
    if action in {"mesaj", "message"}:
        parts = rest.strip().split(" ", 2)
        if len(parts) < 3 or not parts[2].strip():
            return USAGE
        team, member, text = parts
        if team not in store.names():
            return f"'{team}' adlı ekip yok.\n\n{overview(store)}"
        state.engine = Engine.AGENT
        state.pending_task = MESSAGE_TASK.format(team=team, member=member, text=text.strip())
        return f"'{team}' ekibi sürdürülüyor…"
    state.engine = Engine.AGENT
    state.pending_task = BUILD_TASK.format(goal=argument.strip())
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
