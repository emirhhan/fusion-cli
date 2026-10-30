"""Prompt önbelleği — aynı istek tekrar gelirse modeli çağırmadan yanıt ver.

Tam-eşleşme (çözülmüş model + mesajlar + araçlar + sıcaklık + max_tokens) LRU önbellek.
Token ve süre tasarrufu sağlar; tekrar eden isteklerde (araçların aynı bağlamı ikinci kez sorması,
yeniden denemeler) anında yanıt döner. Yalnızca gateway'i etkiler.

Araç çağrısı içeren ya da boş yanıtlar ÖNBELLEĞE ALINMAZ: onlar bağlama bağlıdır ve
tekrar kullanılmamalıdır.
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict

from ..core.types import CompletionRequest, ModelResult


class PromptCache:
    """Basit LRU tam-eşleşme prompt önbelleği (yalnız gateway)."""

    def __init__(self, max_size: int = 200) -> None:
        self._store: OrderedDict[str, ModelResult] = OrderedDict()
        self._max = max_size

    def _key(self, model: str, request: CompletionRequest) -> str:
        # Anahtar ARAÇLARI da kapsar. Ölçüldü (30 Ekim): `tools`, mesajlardaki
        # `tool_calls`/`tool_call_id`/`name` ve görseller anahtarda yoktu; aynı mesajlarla
        # farklı araç listesi gönderen istemci eski düz metin cevabı alıyor, boş içerikli
        # araç çağrılı mesajlar çakışıyordu (E1-13).
        payload = json.dumps(
            {
                "model": model,
                "messages": [
                    (
                        m.role,
                        m.content,
                        m.name,
                        m.tool_call_id,
                        [(c.id, c.name, c.arguments) for c in m.tool_calls],
                        m.images,
                    )
                    for m in request.messages
                ],
                "tools": request.tools,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "reasoning_effort": request.reasoning_effort,
                "disable_thinking": request.disable_thinking,
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(self, model: str, request: CompletionRequest) -> ModelResult | None:
        key = self._key(model, request)
        result = self._store.get(key)
        if result is not None:
            self._store.move_to_end(key)
        return result

    def put(self, model: str, request: CompletionRequest, result: ModelResult) -> None:
        # Yalnızca kullanılabilir, düz metin yanıtlar önbelleklenir.
        if not result.ok or result.tool_calls or not result.text:
            return
        key = self._key(model, request)
        self._store[key] = result
        self._store.move_to_end(key)
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    def __len__(self) -> int:
        return len(self._store)
