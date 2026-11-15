"""Kabul edilen isteğin teslimat amacı; araç çıktısından türetilmez."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ContactIntent(StrEnum):
    UNSPECIFIED = "unspecified"
    DEMO_NO_SEND = "demo_no_send"


@dataclass(frozen=True, slots=True)
class AcceptedDeliveryContract:
    root: Path
    owner: str
    accepted_id: str
    task: str
    contact: ContactIntent = ContactIntent.UNSPECIFIED
    document_output: str | None = None


@dataclass(slots=True)
class DeliveryContractState:
    accepted: AcceptedDeliveryContract | None = None

    def for_owner(self, root: Path, owner: str) -> AcceptedDeliveryContract | None:
        contract = self.accepted
        if contract is not None and contract.root == root.resolve() and contract.owner == owner:
            return contract
        return None
