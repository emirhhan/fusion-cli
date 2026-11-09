"""İç düzeltmelerin kullanıcıya teslim edilecek belgenin yerini almasını önle."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

from ...core.delivery_contract import AcceptedDeliveryContract, ContactIntent
from ...core.text_fold import fold_tr
from .response_format import requested_response_format
from .teacher_plan import short_static_report_output

if TYPE_CHECKING:
    from ...core.tools import ToolContext
    from .turn_report import TurnReport

_QUOTED = re.compile(r'```.*?```|`[^`]*`|^[ \t]*>[^\n]*|["“][^"”\n]*["”]|‘[^’\n]*’', re.M | re.S)
_CONTACT_DEMO = re.compile(
    r"\b(?:iletisim\w*|contact\w*|form\w*)\b[^.!?;\n]{0,100}\bdemo"
    r"(?:\s+olsun\b|\s+oldugunu[^.!?;\n]{0,50}\bsoylesin\b|\s+only\b|(?=\s*[:;.!?]|$))"
)
_POSITIVE_SEND = r"(?:gonder\w*|ilet(?:in|iniz|ilsin)?|iletil\w*|send\w*|sent|deliver\w*|submit\w*)"
_NO_SEND = re.compile(
    r"\b(?:mesaj\w*|ileti\w*|veri\w*)\b"
    rf"(?:(?!\b{_POSITIVE_SEND}\b)[^.!?;\n]){{0,70}}"
    r"\b(?:gonderme|gondermesin|gonderilmesin|gonderilmez|"
    r"gonderilmedigini|gonderilmis gibi davranmasin|gercekten gonderilmez)\b"
    r"|\b(?:no messages? (?:is |are )?sent|do not send|don.t send|nothing (?:is )?sent|no.send)\b"
)
_REJECT_DEMO = re.compile(
    r"\bdemo\s+(?:olmasin|degil|istemiyorum)\b|\b(?:not|no|never)\s+(?:a\s+)?demo\b|don.t[^.!?;\n]{0,30}\bdemo\b"
)
_REAL_SEND = re.compile(rf"\b{_POSITIVE_SEND}\b")
_REJECTED_NO_SEND = re.compile(r"\s+(?:demiyorum|demedim|degil|istemi(?:yorum|yoruz))\b")


def accept_delivery_contract(context: ToolContext, task: str) -> AcceptedDeliveryContract:
    """Yalnız kök kullanıcı turunda çağrılır; önceki turun niyetini sıfırlar."""
    task_prose = re.sub(r"(?<!\w)'[^'\n]+'(?!\w)", " ", _QUOTED.sub(" ", task))
    prose = fold_tr(task_prose).translate(str.maketrans("çğıöşü", "cgiosu"))
    demo = bool(
        _CONTACT_DEMO.search(prose)
        and _NO_SEND.search(prose)
        and not any(
            _REJECTED_NO_SEND.match(prose, match.end()) for match in _NO_SEND.finditer(prose)
        )
        and not _REJECT_DEMO.search(prose)
        and not _REAL_SEND.search(_NO_SEND.sub(" ", prose))
    )
    contract = AcceptedDeliveryContract(
        root=context.root.resolve(),
        owner=context.job_scope,
        accepted_id=uuid4().hex,
        task=task,
        contact=ContactIntent.DEMO_NO_SEND if demo else ContactIntent.UNSPECIFIED,
        document_output=short_static_report_output(task),
    )
    context.delivery_contract.accepted = contract
    return contract


def repaired_document_text(
    context: ToolContext, report: TurnReport, task: str, *, successful: bool
) -> str | None:
    """Eski araştırma olgularını kopyalamadan son ölçülmüş dosyayı teslim et."""
    contract = context.delivery_contract.for_owner(context.root, context.job_scope)
    if contract is None or contract.task != task or requested_response_format(task) is not None:
        return None
    output = contract.document_output
    if output is None or report.changed_paths != (output,) or not (context.root / output).is_file():
        return None
    if report.false_claim:
        return (
            f"Rapor dosyası: `{output}`. "
            "Dosya kontrolleri tamamlandı; ek başarı iddiası doğrulanamadı."
        )
    if successful and report.is_verified is True:
        return f"Rapor hazır: `{output}`. Dosyanın son hali kontrol edildi."
    return (
        f"Rapor dosyası: `{output}`. Son hali bütünüyle doğrulanamadı; kontrol sonuçları yukarıda."
    )
