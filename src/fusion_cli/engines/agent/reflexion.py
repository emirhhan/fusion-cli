"""Refleksiyon — araç hatasından sonra modele yön veren not.

EK MODEL ÇAĞRISI YAPMAZ: yalnızca geçmişe kısa bir kullanıcı mesajı enjekte eder.
Amaç, modelin aynı hatalı çağrıyı körlemesine tekrarlamasını önlemektir; bu bedava
bir davranış düzeltmesidir.

`goal` kipinde daha ısrarcı bir varyant kullanılır: orada pes etmek yasaktır.
"""

from __future__ import annotations

import re

from ...core.types import Message

#: Somut teslim işaretleri: kod parçası, dosya:satır referansı ya da dosya yolu.
#: Kısa ama SOMUT bir cevap ("src/app.py:42") yarım kalmış sayılmamalıdır.
_CONCRETE_MARKERS = (
    re.compile(r"`"),  # satır içi kod ya da kod bloğu
    re.compile(r"\S+\.\w{1,6}:\d+"),  # dosya:satır referansı
    re.compile(r"\S+/\S+\.\w{1,6}"),  # dosya yolu
)

STANDARD_NOTE = (
    "[refleksiyon] Son araç çağrılarından en az biri HATA döndürdü. Kısaca ne yanlış "
    "gitti düşün ve FARKLI bir yaklaşım dene — aynı çağrıyı birebir tekrarlama. "
    "Gerekirse önce keşif yap (read_file / search_code), sonra hedefli düzelt."
)

PERSISTENT_NOTE = (
    "[refleksiyon] Son araç çağrısı HATA döndürdü. Pes etme: hatayı dikkatlice oku ve "
    "farklı bir yol, araç ya da parametre dene. Kendi başına aşamayacağın bir durumsa "
    "ask_user ile kullanıcıdan destek iste."
)

#: Bu uzunluğun altındaki cevaplar "somut teslim" içermiyorsa yarım sayılır.
SHORT_ANSWER_CHARS = 80

AUTO_CONTINUE_NOTE = (
    "[otomatik-devam] İşi yarım bıraktın gibi görünüyor. Niyet beyan etmek yerine ya bir "
    "araç çağırıp devam et ya da somut nihai teslimi ver. Zaten bittiyse tek cümleyle teyit et."
)


def note(*, persistent: bool) -> Message:
    """Araç hatasından sonra enjekte edilecek refleksiyon mesajı."""
    return Message("user", PERSISTENT_NOTE if persistent else STANDARD_NOTE)


def auto_continue_note() -> Message:
    return Message("user", AUTO_CONTINUE_NOTE)


def looks_unfinished(
    final_text: str, *, tool_calls_last_turn: int, has_pending_todos: bool
) -> bool:
    """Model araçsız bitirdi ama iş açıkça yarım mı?

    Dil-bağımsız sezgiseller:
    - Tamamlanmamış todo maddesi varsa iş bitmemiştir.
    - Bu turda araç çağrıldıysa ve nihai metin hem KISA hem de SOMUT bir teslim
      içermiyorsa, model işe başlayıp bitirmeden durmuş olabilir.

    "Somut teslim" kontrolü kritik: `src/app.py:42` gibi kısa ama tam bir cevabı
    yarım sanıp modeli tekrar konuşturmak, aynı cevabın iki kez basılmasına yol açar.
    """
    if has_pending_todos:
        return True
    text = final_text.strip()
    return (
        tool_calls_last_turn > 0
        and len(text) < SHORT_ANSWER_CHARS
        and not has_concrete_deliverable(text)
    )


def has_concrete_deliverable(text: str) -> bool:
    """Metin somut bir teslim taşıyor mu? (kod, dosya yolu ya da dosya:satır)"""
    return any(marker.search(text) for marker in _CONCRETE_MARKERS)


#: Boş cevap sonrası modele verilen dürtü. Suçlayıcı değil yönlendirici: model
#: cevabı neden düşürdüğünü bilmiyor, tekrar denemesi isteniyor.
EMPTY_RESPONSE_NOTE = (
    "Boş bir cevap döndürdün. Göreve devam et: ya bir araç çağır ya da "
    "yaptıklarını özetleyen bir cevap yaz."
)


def empty_response_note() -> Message:
    """Boş cevaptan sonra enjekte edilen kullanıcı notu."""
    return Message("user", EMPTY_RESPONSE_NOTE)


_EFFECT_LABELS = {
    "git_push": "Git uzak deposunu güncelleme (başarılı bir `git push`)",
    "git_commit": "Git commit oluşturma (başarılı bir `git commit`)",
    "shell_action": "istenen komut/sistem işlemi (başarılı `run_shell`)",
    "workspace_mutation": "çalışma alanını değiştirme (başarılı değiştirici araç)",
    "web_lookup": "web araştırması (başarılı `web_search` veya `web_fetch`)",
    "workspace_read": "çalışma alanını inceleme (başarılı okuma/arama aracı)",
}


def tool_evidence_required_note(effect: str | None) -> Message:
    """Model eylem sözü verdi ama gerçek araç çalıştırmadıysa bir kez zorla."""

    label = _EFFECT_LABELS.get(effect or "", "kullanıcının istediği gerçek işlem")
    return Message(
        "user",
        "[eylem-kanıtı-zorunlu] Kullanıcı gerçek bir işlem istedi fakat henüz "
        f"{label} için başarılı bir araç sonucu yok. 'Kontrol ediyorum', 'yapıyorum', "
        "'güncelliyorum' gibi niyet cümleleriyle bitirme. Şimdi uygun aracı canonical "
        "<tool_call>{...}</tool_call> biçiminde çağır. İşlem için bilgi/onay eksikse "
        "ask_user kullan. Aracı kullanamıyorsan işlemin yapılmadığını açıkça söyle; "
        "yapılmış gibi davranma.",
    )


def unverified_action_message(effect: str | None) -> str:
    """İki araçsız denemeden sonra kullanıcıya dürüst ve kesin sonuç ver."""

    label = _EFFECT_LABELS.get(effect or "", "istenen işlem")
    return (
        f"İşlem tamamlanmadı: {label} için başarılı bir araç çağrısı doğrulanamadı. "
        "Herhangi bir değişiklik yapılmış veya uzak sistem güncellenmiş kabul edilmemelidir."
    )




def tool_contract_repair_note(detail: str) -> Message:
    """Give a web model one precise chance to repair a malformed call."""
    return Message(
        "user",
        "[tool-contract-repair] Önceki araç çağrın geçersizdi. "
        f"Hata: {detail}\n"
        "Yalnızca bir kez düzelt.\n"
        "Kısa çağrı örneği:\n"
        '<tool_call>{"name":"read_file","arguments":'
        '{"path":"src/app.py"}}</tool_call>\n'
        "Çok satırlı kodu JSON stringine koyma. Payload kullan:\n"
        '<tool_payload id="file-1">\n'
        "def example():\n"
        '    print("ok")\n'
        "</tool_payload>\n"
        '<tool_call>{"name":"write_file","arguments":'
        '{"path":"example.py","content":{"$ref":"file-1"}}}</tool_call>\n'
        "Payload ham metindir; JSON escape veya Markdown fence kullanma. "
        "Her id benzersiz ve referanslı olmalı. Aynı geçersiz çağrıyı tekrarlama. "
        "Düzeltemiyorsan işlemin tamamlanmadığını açıkça söyle.",
    )
