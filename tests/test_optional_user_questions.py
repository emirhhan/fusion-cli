"""İsteğe bağlı soru cevabı uydurmaz ve kendi görevini temizler."""

from __future__ import annotations

import asyncio

from fusion_cli.engines.agent.questions import PendingUserQuestions, QuestionState


async def test_optional_question_allows_independent_work_and_cancels_on_close():
    owner = PendingUserQuestions()
    future = asyncio.get_running_loop().create_future()
    receipt = owner.start(future)
    assert receipt.state is QuestionState.PENDING
    assert owner.pending
    independent = []
    independent.append("salt okuma tamamlandı")
    assert independent
    await owner.close()
    assert future.cancelled()
    assert not owner.pending


async def test_only_explicit_answer_is_returned_once():
    owner = PendingUserQuestions()
    future = asyncio.get_running_loop().create_future()
    owner.start(future)
    future.set_result("seçtiğim hedef")
    await asyncio.sleep(0)
    results = owner.drain()
    assert len(results) == 1
    assert results[0].state is QuestionState.ANSWERED
    assert results[0].text == "seçtiğim hedef"
    assert owner.drain() == ()
    await owner.close()


async def test_cancelled_question_channel_does_not_cancel_independent_work():
    """Soru kanalının kapanışı, turun kendisinin iptal edilmesi değildir."""
    owner = PendingUserQuestions()
    answer = asyncio.get_running_loop().create_future()
    owner.start(answer)
    answer.cancel()
    await asyncio.sleep(0)
    (result,) = owner.drain()
    assert result.state is QuestionState.UNAVAILABLE
    assert result.text == ""
    assert not owner.pending
    await owner.close()
