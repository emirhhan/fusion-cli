"""İçe aktarma önizlemesinin ve sonucunun metni (P-071): CLI ve REPL aynı metni görür."""

from __future__ import annotations

from ..config.importers import ImportPlan, ImportReport, ImportStatus

HEADER = "İçe aktarma önizlemesi · {source}"
EMPTY = "{source}: Fusion'a taşınacak bir yapılandırma bulunamadı."
NOTHING_NEW = "Taşınacak yeni bir şey yok."
PENDING = "{count} öğe eklenecek."
APPLY_HINT = "Uygulamak için: {command} --yes"
APPLIED = "İçe aktarıldı: {count} öğe."
FAILED = "  ✗ {name}: {reason}"
WRITTEN = "Yazılan dosyalar: {paths}"
RESTART = "MCP sunucuları Fusion yeniden başlayınca bağlanır; ilk araç çağrıları onay ister."
WARNING = "  ! {text}"

#: Durum → satır başı işareti.
_MARKS = {
    ImportStatus.NEW: "+",
    ImportStatus.EXISTS: "=",
    ImportStatus.NATIVE: "✓",
    ImportStatus.SKIPPED: "–",
}


def format_plan(plan: ImportPlan, *, command: str = "") -> str:
    if not plan.items and not plan.warnings:
        return EMPTY.format(source=plan.source)
    rows = [HEADER.format(source=plan.source)]
    for item in plan.items:
        detail = f" · {item.detail}" if item.detail else ""
        rows.append(
            f"  {_MARKS[item.status]} [{item.kind.value}] {item.name} — {item.status.value}{detail}"
        )
    rows.extend(WARNING.format(text=text) for text in plan.warnings)
    pending = len(plan.pending)
    rows.append(PENDING.format(count=pending) if pending else NOTHING_NEW)
    if pending and command:
        rows.append(APPLY_HINT.format(command=command))
    return "\n".join(rows)


def format_report(report: ImportReport) -> str:
    rows = [APPLIED.format(count=len(report.applied))]
    rows.extend(FAILED.format(name=item.name, reason=reason) for item, reason in report.failed)
    if report.written:
        rows.append(WRITTEN.format(paths=", ".join(str(path) for path in report.written)))
    if any(item.kind.value == "mcp" for item in report.applied):
        rows.append(RESTART)
    return "\n".join(rows)
