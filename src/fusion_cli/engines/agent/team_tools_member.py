"""Ekip üyesinin pano araçları (P-061): `team_board`, `team_task`, `team_send`.

Yalnız ekip üyesinin çalışma-anı defterine eklenir (ana ajan bunları görmez); her araç
o üyenin adına bağlıdır, model başka üye adına görev alamaz. Pano `.fusion/ekip/`
altındadır, proje dosyası değildir: araçlar değiştirici sayılmaz (salt okuyan üye de
görev alıp bitirebilir), `todo_write` ile aynı sınıf.
"""

from __future__ import annotations

from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from .arg_coerce import coerce_bool, coerce_list
from .team_board import BROADCAST, LEAD, TeamBoard, TeamError
from .team_session import TeamSession

#: Rol kısıtı olan (ör. `tools:` listeli) üyeye de her zaman açık koordinasyon araçları.
TEAM_MEMBER_TOOLS = frozenset({"team_board", "team_task", "team_send"})
_STRING = {"type": "string"}


def member_tools(session: TeamSession, member: str) -> tuple[Tool, ...]:
    return (_board_tool(session, member), _task_tool(session, member), _send_tool(session, member))


def render_board(board: TeamBoard, viewer: str) -> str:
    lines = [
        f"Ekip: {board.name} — hedef: {board.goal}",
        "Üyeler: "
        + ", ".join(
            f"{member.name}{' (sen)' if member.name == viewer else ''}" for member in board.members
        ),
        "Görevler:",
    ]
    for task in board.tasks:
        mark = " ← alabilirsin" if board.is_claimable(task, viewer) else ""
        deps = f" bağımlı: {', '.join(task.depends_on)}" if task.depends_on else ""
        who = (
            f" sahip: {task.owner}"
            if task.owner
            else (f" atanan: {task.assignee}" if task.assignee else "")
        )
        lines.append(f"- {task.id} {task.status}{who}{deps}: {task.title}{mark}")
        if task.description:
            lines.append(f"    {task.description[:400]}")
    return "\n".join(lines)


def _board_tool(session: TeamSession, member: str) -> Tool:
    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        unread = await session.take_inbox(member)
        text = render_board(session.board, member)
        if unread:
            text += "\n\nGelen kutusu (yeni):\n" + "\n".join(
                f"- {message.sender}: {message.text}" for message in unread
            )
        else:
            text += "\n\nGelen kutusu: yeni mesaj yok."
        return ToolResult(text)

    return Tool(
        name="team_board",
        description="Ekip panosunu (görevler, sahipler, bağımlılıklar) ve sana gelen yeni "
        "mesajları göster; mesajlar okundu sayılır.",
        parameters={"type": "object", "properties": {}},
        run=_run,
    )


def _task_tool(session: TeamSession, member: str) -> Tool:
    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        action = str(args.get("eylem") or "").strip().casefold()
        task_id = str(args.get("id") or "").strip()
        try:
            if action == "al":
                task = await session.claim(member, task_id)
                body = f"\n{task.description}" if task.description else ""
                return ToolResult(f"{task.id} senin: {task.title}{body}")
            if action == "bitir":
                if not task_id:
                    return ToolResult.failure("'bitir' için görev 'id' gerekli.")
                ok = coerce_bool(args.get("basarili", True)) is not False
                task = await session.finish(member, task_id, str(args.get("sonuc") or ""), ok=ok)
                return ToolResult(f"{task.id} {task.status}. Sıradaki görevi al ya da bitir.")
            if action == "ekle":
                deps = coerce_list(args.get("bagimli", []))
                task = await session.add_task(
                    member,
                    str(args.get("baslik") or ""),
                    description=str(args.get("aciklama") or ""),
                    depends_on=tuple(str(dep) for dep in deps) if isinstance(deps, list) else (),
                    assignee=str(args.get("atanan") or "").strip(),
                )
                return ToolResult(f"{task.id} eklendi: {task.title}")
        except TeamError as error:
            return ToolResult.failure(str(error))
        return ToolResult.failure("'eylem' al, bitir ya da ekle olmalı.")

    return Tool(
        name="team_task",
        description="Paylaşımlı görev listesi: eylem 'al' (id yoksa sıradaki uygun görev), "
        "'bitir' (id, sonuc, basarili) ya da 'ekle' (baslik, aciklama, bagimli, atanan).",
        parameters={
            "type": "object",
            "properties": {
                "eylem": {"type": "string", "enum": ["al", "bitir", "ekle"]},
                "id": _STRING,
                "sonuc": _STRING,
                "basarili": {"type": "boolean"},
                "baslik": _STRING,
                "aciklama": _STRING,
                "bagimli": {"type": "array", "items": _STRING},
                "atanan": _STRING,
            },
            "required": ["eylem"],
        },
        run=_run,
    )


def _send_tool(session: TeamSession, member: str) -> Tool:
    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        recipient = str(args.get("kime") or "").strip().casefold()
        try:
            targets = await session.send(member, recipient, str(args.get("metin") or ""))
        except TeamError as error:
            return ToolResult.failure(str(error))
        return ToolResult(f"Gönderildi: {', '.join(targets)}")

    return Tool(
        name="team_send",
        description=f"Ekip arkadaşına, lidere ('{LEAD}') ya da herkese ('{BROADCAST}') kısa "
        "mesaj gönder; alıcı boştaysa uyandırılır.",
        parameters={
            "type": "object",
            "properties": {"kime": _STRING, "metin": _STRING},
            "required": ["kime", "metin"],
        },
        run=_run,
    )
