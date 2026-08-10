"""Karmaşık bir görevde HİÇ araç çağırmayan tur "başarılı" sayılmaz.

Ölçüldü (canlı koşu): model üç tur boyunca "somut bir görev almadım, dizin
içeriğini listeliyorum" tarzı düz yazı üretti ve tek bir dosya değişmedi. Turun
`ok=True` ile kapanmasını hiçbir kapı engellemedi.

Sebep, iki kapının da sıfır çağrıyı DIŞARIDA bırakması:

  - `_stopped_without_acting` → `state.tool_calls_made == 0` ise False döner.
  - `_asked_instead_of_acting` → aynı şekilde False döner.

İkisi de "araç çağırdı ama hiçbir şey değiştirmedi" durumunu yakalamak için
yazılmış; oysa en kötü durum "hiç araç çağırmadı"dır ve tam olarak o durum
kapsam dışında kalıyordu. Kanıt kapısı (`requires_tool_evidence`) da yalnızca
görevden somut bir etki çıkarılabildiğinde açılıyor, yani her görevde değil.
"""

from __future__ import annotations

from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.loop import _never_acted, _State


def _politika(*, complex_task: bool) -> ExecutionPolicy:
    return ExecutionPolicy(is_web=True, complex_task=complex_task)


def test_karmasik_gorevde_sifir_cagri_yakalanir() -> None:
    durum = _State()

    assert _never_acted(durum, _politika(complex_task=True)) is True


def test_arac_cagrildiysa_bu_kapi_konusmaz() -> None:
    """Bu kapı YALNIZCA sıfır çağrı içindir; gerisi diğer kapıların işi."""
    durum = _State(tool_calls_made=2)

    assert _never_acted(durum, _politika(complex_task=True)) is False


def test_basit_gorevde_zorlanmaz() -> None:
    """"Bu dosya ne yapıyor" gibi bir soru araçsız cevaplanabilir."""
    durum = _State()

    assert _never_acted(durum, _politika(complex_task=False)) is False


def test_ic_duzeltici_turda_konusmaz() -> None:
    """İç tur araçsız bitebilir: asıl işi dış tur yapmıştır, iç tur düzeltir."""
    durum = _State(internal=True)

    assert _never_acted(durum, _politika(complex_task=True)) is False


def test_kapi_bir_kez_konusur() -> None:
    """Sonsuz döngü olmaz: model ikinci kez de araçsız gelirse tur biter."""
    durum = _State(never_acted_prompts=1)

    assert _never_acted(durum, _politika(complex_task=True)) is False
