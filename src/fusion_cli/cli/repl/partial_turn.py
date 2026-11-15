"""Yarıda kesilen ya da hatayla biten turun geçmişini korur.

Tur normal bitince `outcome.messages` geçmiş olur. Kullanıcı esc/Ctrl-C ile keserse
ya da tur istisnayla biterse `outcome` yoktur; o turun araç sonuçları geçmişe girmez,
model sonraki turda "az önce ne yaptığını" bilmez (L2-12). Döngü her araç turundan
sonra konuşmayı `TurnJournal.save` ile bildirir; bu sınıf onu bellekte tutar ve
masaüstüyle AYNI `interrupted_history` ile kapatır (eksik araç sonucu başarı sayılmaz).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ...core.turn_resume import interrupted_history
from ...core.types import Message


class PartialTurn:
    """`TurnJournal` protokolünün bellek içi uygulaması: son kaydedilen mesajlar."""

    def __init__(self) -> None:
        self._messages: list[Message] | None = None

    def save(self, messages: Sequence[Message]) -> None:
        self._messages = list(messages)

    def history_after_interruption(
        self, *, previous: Sequence[Message], task: str, root: Path
    ) -> list[Message]:
        """Kesilen turdan sonra sohbet geçmişi olacak mesajlar.

        Döngü hiç kayıt yapmadan kesildiyse (ilk model çağrısı sürerken) geçmiş,
        önceki mesajlar + kullanıcının bu turdaki isteğidir.
        """
        preserved = (
            self._messages if self._messages is not None else [*previous, Message("user", task)]
        )
        return interrupted_history(preserved, task=task, root=str(root.resolve()))
