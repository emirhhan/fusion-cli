"""Local response ratings and persistent conversation branches."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from ..cli.repl.transcript_store import copy_conversation, load_transcript_messages
from ..core.redaction import redact
from ..core.types import Message


def fork_response(
    base: Path, root: Path, source_id: str, history: list[Message], data: dict[str, Any]
) -> dict[str, Any]:
    text = data.get("metin")
    occurrence = data.get("eslesme", 0)
    if not isinstance(text, str) or not text or type(occurrence) is not int or occurrence < 0:
        return {"ok": False, "metin": "Devam edilecek yanıt geçersiz."}
    matches = [
        index
        for index, message in enumerate(history)
        if message.role == "assistant" and redact(message.content) == redact(text)
    ]
    if occurrence >= len(matches):
        # İptal/fallback yanıtının ekranda görünen son metni diske yazılır;
        # model bağlamındaki açıklama farklı olabilir.
        history = load_transcript_messages(base, root, conversation_id=source_id)
        matches = [
            index
            for index, message in enumerate(history)
            if message.role == "assistant" and message.content == redact(text)
        ]
    if occurrence >= len(matches):
        return {"ok": False, "metin": "Yanıt sohbet geçmişinde bulunamadı."}
    prefix = [
        message
        for message in history[: matches[occurrence] + 1]
        if message.role in {"user", "assistant"} and message.content.strip()
    ]
    if not any(message.role == "user" for message in prefix):
        return {"ok": False, "metin": "Devam edilecek kullanıcı mesajı bulunamadı."}
    target_id = str(uuid.uuid4())
    # Kopyalama çekirdeği CLI `/branch` ve `--fork-session` ile ortak (P-014); doğrulama
    # başarısızsa yarım sohbeti o siler.
    try:
        count = copy_conversation(base, root, prefix, target_id=target_id)
    except (ValueError, OSError):
        return {"ok": False, "metin": "Yeni sohbet geçmişi kaydedilemedi."}
    return {
        "ok": True,
        "sohbet_id": target_id,
        "kaynak_sohbet_id": source_id,
        "kok": str(root),
        "mesaj_sayisi": count,
    }


def save_rating(base: Path, conversation_id: str, data: dict[str, Any]) -> dict[str, Any]:
    text, rating = data.get("metin"), data.get("rating")
    if not isinstance(text, str) or not text or rating not in ("positive", "negative"):
        return {"ok": False, "metin": "Yanıt değerlendirmesi geçersiz."}
    record = {
        "conversation_id": conversation_id,
        "rating": rating,
        "answer_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "timestamp": time.time(),
    }
    try:
        directory = base / "feedback"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(
            directory / "response-ratings.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600
        )
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        return {"ok": False, "metin": "Yanıt değerlendirmesi kaydedilemedi."}
    return {"ok": True, "rating": rating}
