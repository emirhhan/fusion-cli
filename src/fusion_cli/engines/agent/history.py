"""Konuşma geçmişi üzerinde saf işlemler.

Ağ ve model çağrısı yoktur; doğrudan test edilir. Buradaki iki kural, uzun oturumları
bozan iki klasik hatayı önler:

1. **Kesme noktası bir `user` turunun başında olmalıdır.** Bir `assistant` mesajı araç
   çağrısı taşıyorsa onu izleyen `tool` sonuçlarından ayrılamaz; ayrılırsa sağlayıcı
   "orphan tool call" hatası verir. Bu yüzden kesim daima güvenli sınıra kaydırılır.
2. **Sıkıştırma başarısızsa geçmişe dokunulmaz.** Yarım özet, hiç özetten kötüdür.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace

from ...core.types import Message

#: Geçmiş bu karakter sayısını aşınca sıkıştırma denenir.
#:
#: Değer havuzun EN DAR bağlam penceresinden türetilir; en genişinden değil, çünkü
#: yedeğe düşen tur da aynı geçmişi taşır. En dar pencere ÖLÇÜLDÜĞÜNDE (2026-07-25)
#: gpt-oss-20b'de 131.072 token idi (karşılaştırma: nemotron-3-super 262.144–1.000.000).
#: 2026-09-22: gpt-oss-20b havuzdan çıkarıldı (OpenRouter'da 404, ücretsiz slug
#: kaldırılmış — bkz. `config/defaults.yaml`). Yerine geçen `qwen3.8-27b:free`
#: penceresi 262.144 token, yani DAHA GENİŞ — değer hâlâ ihtiyatlı tarafta,
#: küçültülmesi gerekmiyor.
#:
#:   kullanılabilir ≈ 131.072 − çıktı bütçesi (8.192) − sistem promptu + araç şemaları (~4.000)
#:                  ≈ 119.000 token
#:   geçmişe ayrılan ≈ yarısı ≈ 59.000 token
#:   Türkçe + kod için ihtiyatlı oran 3 karakter/token ≈ 177.000 karakter
#:
#: Eski değer 24.000 karakterdi (≈6k token): en dar pencerenin bile %5'i. Agent üç beş
#: dosya okur okumaz geçmişini bir özete indiriyor, az önce okuduğunu unutuyordu.
COMPRESS_THRESHOLD_CHARS = 177_000
#: Sıkıştırmada birebir korunacak en son mesaj sayısı.
#:
#: Bir araç turu İKİ mesajdır (çağrı + sonuç), yani 6 yalnızca 3 tur demekti: özet
#: alındığı anda agent son üç adımı dışında her şeyi kaybediyordu. 20 mesaj ≈ 10 araç
#: turu — sıkıştırmadan sonra işe devam edebilecek kadar somut bağlam kalır.
KEEP_RECENT_MESSAGES = 20
#: Oturum izinde tek bir mesajdan alınacak en fazla karakter.
TRACE_MESSAGE_CHARS = 300
#: Başarısız araç sonucuna tanınan pay çarpanı: hata ayrıntısı (neyin neden düştüğü)
#: izin en değerli parçasıdır.
TRACE_ERROR_FACTOR = 2
#: Önceki bir ÖZET mesajının izde taşınacağı üst sınır. Özet zaten sıkıştırılmıştır;
#: 300 karaktere kesmek ardışık sıkıştırmalarda ilk özeti silerdi (A1-02).
TRACE_SUMMARY_CHARS = 10_000
#: Sıkıştırmanın eklediği özet mesajlarının başlıkları (tur arası / tur içi).
CONVERSATION_SUMMARY_PREFIX = "[önceki konuşmanın özeti]"
STEPS_SUMMARY_PREFIX = "[önceki adımların özeti]"
#: Oturum izinin toplam uzunluğu.
TRACE_TOTAL_CHARS = 3_000


#: Web oturumları için sıkıştırma eşiği (30.000 karakterlik web prompt bütçesinin altında).
WEB_COMPRESS_THRESHOLD_CHARS = 24_000


def is_summary_message(message: Message) -> bool:
    """Mesaj, sıkıştırmanın eklediği bir özet mi? (kullanıcı görevi DEĞİLDİR)"""
    return message.role == "user" and message.content.lstrip().startswith(
        (CONVERSATION_SUMMARY_PREFIX, STEPS_SUMMARY_PREFIX)
    )


#: Bir görselin bağlama kabaca katkısı (karakter eşdeğeri). Data URI'nin ham uzunluğu
#: (MB'larca) değil, görsel modelin harcadığı token'a yakın bir tahmin: ekran
#: görüntüsü yüklü turlarda eşik gerçekte aşılırken sıkıştırma tetiklenmiyordu (A1-44).
IMAGE_CHARS_ESTIMATE = 4_000


def total_chars(messages: Sequence[Message]) -> int:
    """Geçmişin kabaca büyüklüğü: içerik ARTI araç çağrısı argümanları.

    Ölçüldü (17. kabul koşusu): yalnız `content` sayılıyordu; `write_file`/
    `edit_file` argümanlarındaki dosya içerikleri (~222 bin karakter, geçmişin
    %43'ü) görünmüyordu. Sayılan ~292 bin karakter eşiğin altında kaldı, gerçek
    ~514 bin; sıkıştırma hiç tetiklenmedi ve istem 185 bin token'a çıktı.
    """
    return sum(
        len(message.content)
        + sum(len(call.arguments) for call in message.tool_calls)
        + IMAGE_CHARS_ESTIMATE * len(message.images)
        for message in messages
    )


def needs_compression(messages: Sequence[Message], threshold_chars: int | None = None) -> bool:
    limit = threshold_chars if threshold_chars is not None else COMPRESS_THRESHOLD_CHARS
    return total_chars(messages) >= limit


def safe_cut(messages: Sequence[Message], keep_recent: int = KEEP_RECENT_MESSAGES) -> int:
    """Son `keep_recent` mesajı korurken güvenli kesme indeksini bul.

    Kesim noktası bir `user` mesajına kaydırılır; araç çağrısı ile sonucu ayrılmaz.
    Güvenli nokta yoksa 0 döner (sıkıştırma yapılmaz).
    """
    start = max(0, len(messages) - keep_recent)
    while start < len(messages) and messages[start].role != "user":
        start += 1
    if start >= len(messages):
        return 0
    unseen = unseen_tool_indexes(messages)
    if unseen:
        group_start = max(
            (
                index
                for index, message in enumerate(messages)
                if message.role == "assistant" and message.tool_calls
            ),
            default=start,
        )
        start = min(start, group_start)
    return start


#: Temizlenen eski araç çıktısının yerine konan not. Model gerekirse yeniden okur.
CLEARED_TOOL_OUTPUT = (
    "[eski araç çıktısı bağlamdan temizlendi ({chars} karakter); gerekirse yeniden oku]"
)


PIN_MAX_CHARS = 1_500


def pin_tool_output(message: Message, pin_chars: int = PIN_MAX_CHARS) -> Message:
    """Eski kanıtın başını sınırlı tut; görseller karakter bütçesini aşmasın."""
    limit = max(0, min(pin_chars, PIN_MAX_CHARS))
    return replace(message, content=message.content[:limit], images=())


def unseen_tool_indexes(messages: Sequence[Message]) -> set[int]:
    """Son assistant araç grubundan sonraki tüm sonuçları koru."""
    tool_indexes = [index for index, message in enumerate(messages) if message.role == "tool"]
    last_call = max(
        (
            index
            for index, message in enumerate(messages)
            if message.role == "assistant" and message.tool_calls
        ),
        default=None,
    )
    if last_call is None:
        return set(tool_indexes[-1:])
    return {index for index in tool_indexes if index > last_call}


def clear_old_tool_outputs(
    messages: Sequence[Message],
    threshold_chars: int | None = None,
    *,
    pinned_call_ids: frozenset[str] = frozenset(),
    pin_chars: int = PIN_MAX_CHARS,
) -> list[Message]:
    """En ESKİ araç çıktılarından başlayarak geçmişi eşiğin altına indir.

    Claude Code'un belgelenmiş davranışı: bağlam dolarken "önce eski araç
    çıktılarını temizler, gerekirse sonra konuşmayı özetler". Çıktı en büyük ve
    en kolay yeniden üretilen parçadır: dosya yeniden okunabilir, ama modelin
    kararları ve kullanıcının istekleri yeniden üretilemez.

    Sabit bir "son N mesajı koru" penceresi kullanılmaz: ölçüldü, 24 KB'lık birkaç
    okuma 20 mesajlık pencereye sığıyor ve hiçbir şey temizlenemiyordu. Eşiğe
    inilene kadar eskiden yeniye temizlenir; EN SON araç çıktısına hiç dokunulmaz,
    çünkü model bir sonraki adımı ona bakarak atar. Mesaj silinmez, yalnız içeriği
    kısalır; araç çağrısı ile sonucu arasındaki eşleşme bozulmaz.
    """
    limit = threshold_chars if threshold_chars is not None else COMPRESS_THRESHOLD_CHARS
    sonuc = list(messages)
    unseen = unseen_tool_indexes(sonuc)
    temizlenebilir = [
        index
        for index, message in enumerate(sonuc)
        if message.role == "tool" and index not in unseen
    ]
    toplam = total_chars(sonuc)
    for index in temizlenebilir:
        if toplam < limit:
            break
        message = sonuc[index]
        if message.tool_call_id in pinned_call_ids:
            replacement = pin_tool_output(message, pin_chars)
        else:
            note = CLEARED_TOOL_OUTPUT.format(chars=len(message.content))
            if len(message.content) <= len(note):
                continue
            replacement = replace(message, content=note)
        sonuc[index] = replacement
        toplam -= total_chars([message]) - total_chars([replacement])
    if toplam >= limit:
        sonuc = _stub_old_tool_arguments(sonuc, toplam, limit)
    return sonuc


#: Bu uzunluğu aşan eski araç argümanı alanları (dosya içeriği, düzenleme metni)
#: taslağa indirilir; yol ve kısa alanlar korunur ki model ne yaptığını bilsin.
STUB_FIELD_MIN_CHARS = 400
STUBBED_FIELD = "[bağlamdan temizlendi: {chars} karakter; içerik dosyada, gerekirse oku]"


def _stub_arguments(arguments: str) -> str:
    """JSON argümandaki uzun metin alanlarını taslağa indir; JSON geçerli kalır."""
    try:
        veri = json.loads(arguments)
    except ValueError:
        return arguments
    if not isinstance(veri, dict):
        return arguments
    kisaltilmis = {
        anahtar: STUBBED_FIELD.format(chars=len(deger))
        if isinstance(deger, str) and len(deger) > STUB_FIELD_MIN_CHARS
        else deger
        for anahtar, deger in veri.items()
    }
    return json.dumps(kisaltilmis, ensure_ascii=False)


def _stub_old_tool_arguments(messages: list[Message], toplam: int, limit: int) -> list[Message]:
    """Eski assistant mesajlarının büyük araç argümanlarını eskiden yeniye kısalt.

    Araç çıktıları temizlendikten sonra hâlâ eşik aşılıyorsa çağrılır. EN SON
    assistant mesajına dokunulmaz (model bir sonraki adımı ona bakarak atar).
    Çağrı kimliği ve adı korunur; çağrı-sonuç eşleşmesi bozulmaz.
    """
    indeksler = [i for i, m in enumerate(messages) if m.role == "assistant" and m.tool_calls]
    for index in indeksler[:-1]:
        if toplam < limit:
            break
        message = messages[index]
        cagrilar = tuple(
            replace(call, arguments=_stub_arguments(call.arguments)) for call in message.tool_calls
        )
        once = sum(len(call.arguments) for call in message.tool_calls)
        sonra = sum(len(call.arguments) for call in cagrilar)
        if sonra < once:
            messages[index] = replace(message, tool_calls=cagrilar)
            toplam -= once - sonra
    return messages


def task_anchor_length(messages: Sequence[Message]) -> int:
    """Tur İÇİ sıkıştırmada korunacak baş: sistem mesajı ve ilk görev mesajı.

    `root_anchor_length` ikinci kullanıcı mesajına kadar HER ŞEYİ korur; tek ve
    uzun bir turda ikinci kullanıcı mesajı olmadığından turun tamamı "kök" sayılır
    ve hiçbir şey özetlenemezdi (ölçüldü, 28 Eylül: büyük görevde bağlam sonuna
    kadar büyüdü). Tur içinde korunması gereken yalnız kimlik ve görevdir.
    """
    for index, message in enumerate(messages):
        if message.role == "user" and not message.harness_note:
            return index + 1
    return 0


def round_cut(messages: Sequence[Message], keep_recent: int = KEEP_RECENT_MESSAGES) -> int:
    """Son `keep_recent` mesajı koruyarak bir ARAÇ TURU sınırında kesme indeksi bul.

    Tur içinde kullanıcı mesajı az olduğu için kesim bir asistan mesajının başına
    da yapılabilir: asistan mesajı yeni bir turu başlatır, araç çağrısı ile
    sonucu ayrılmaz. Güvenli nokta yoksa 0 döner.
    """
    start = max(0, len(messages) - keep_recent)
    while start < len(messages) and messages[start].role not in {"user", "assistant"}:
        start += 1
    if start >= len(messages):
        return 0
    unseen = unseen_tool_indexes(messages)
    if unseen:
        group_start = max(
            (
                index
                for index, message in enumerate(messages)
                if message.role == "assistant" and message.tool_calls
            ),
            default=start,
        )
        start = min(start, group_start)
    return start


def root_anchor_length(messages: Sequence[Message]) -> int:
    """Kök konuşmanın (sistem mesajı + ilk kullanıcı turu) mesaj sayısı.

    Bu bölüm sıkıştırmaya asla girmez. Ölçüldü ("MAVİ-KEDİ" vakası): uzun bir
    plan turunda sıkıştırma eşiği aşılınca kesim noktasından ÖNCEKİ HER ŞEY
    (sistem mesajı ve kullanıcının kök turda söylediği "hatırla" talimatı
    dahil) TEK bir olasılıksal özetleyici çağrısına emanet ediliyordu.
    Özetleyici bir LLM'dir ve gördüğü ayrıntıyı yazmayı GARANTİ ETMEZ; kök
    talimat özete girmeyince telafisiz kayboluyordu. Sistem kimliği de aynı
    kaderi paylaşıyor, `[önceki konuşmanın özeti]` diye bir `user` mesajıyla
    değiştiriliyordu.

    Bağlam notları kullanıcı turu sayılmaz. İkinci gerçek kullanıcı mesajına
    kadarki her şey (sistem + ilk soru + o turun
    asistan/araç mesajları) kök turdur ve özetleyiciye değil, olduğu gibi
    kalır. Hiç ikinci `user` yoksa (kısa konuşma) TÜM liste kök turdur.

    Yalnız gerçek bir kök konuşma varsa (mesaj `system` ile başlıyorsa) devreye
    girer: sistem mesajı olmayan bir dizi (ör. iç bir alt-tur izi) korunacak bir
    "kimlik" taşımaz, orada anchor açmak sıradan içeriği de sıkıştırmadan
    muaf tutardı.
    """
    if not messages or messages[0].role != "system":
        return 0
    kullanici_sayisi = 0
    for index, message in enumerate(messages):
        # Önceki özet yeni sıkıştırmaya katılır; ilk görev öncesi bağlam korunur.
        if kullanici_sayisi and is_summary_message(message):
            return index
        if message.role == "user" and not message.harness_note:
            kullanici_sayisi += 1
            if kullanici_sayisi == 2:
                return index
    return len(messages)


#: İz sınıra sığmadığında başa konan işaret. Denetçi eksik bilgiyle çalıştığını bilmeli.
ELISION_NOTE = "[… önceki adımlar atlandı …]"


def transcript(
    messages: Sequence[Message],
    limit: int = TRACE_TOTAL_CHARS,
    *,
    message_chars: int = TRACE_MESSAGE_CHARS,
) -> str:
    """Denetim ve özet için kısa oturum izi çıkar.

    Araç çağrıları ve sonuçları (özellikle hatalar) korunur: denetçi modelin işin
    gerçekten yapılıp yapılmadığını anlaması buna bağlıdır.

    Sınır aşılırsa BAŞTAN değil SONDAN tutulur. Eskiden `[:limit]` ile ilk satırlar
    saklanıyordu; 60 adımlık bir turda denetçiye yalnızca ilk 10 adım gidiyor, üretilen
    hiçbir dosyayı görmeden "TAMAM" diyordu. Bir turun sonucu sonunda olur.
    """
    lines: list[str] = []
    for message in messages:
        lines.extend(_describe(message, message_chars))

    tam = "\n".join(lines)
    if len(tam) <= limit:
        return tam

    # Satır bütünlüğünü koru: sondan başlayarak sığdığı kadar satır al.
    butce = limit - len(ELISION_NOTE) - 1
    tutulan: list[str] = []
    for line in reversed(lines):
        if len(line) + 1 > butce:
            break
        tutulan.append(line)
        butce -= len(line) + 1
    tutulan.reverse()
    return "\n".join([ELISION_NOTE, *tutulan])


def _sample(text: str, limit: int) -> str:
    """`limit`'i aşan metinde baştan VE sondan örnekle (ortası atlanır).

    Araç çıktısında başlık/komut başta, sonuç/hata satırı sonda olur; yalnız baştan
    kesmek ikincisini her zaman siliyordu.
    """
    if len(text) <= limit:
        return text
    bas = (limit * 2) // 3
    son = limit - bas
    return f"{text[:bas]} […] {text[-son:]}"


def _describe(message: Message, message_chars: int = TRACE_MESSAGE_CHARS) -> list[str]:
    excerpt = message.content[:message_chars]
    if message.role == "user" and message.content:
        if is_summary_message(message):
            # Önceki özet KESİLMEZ: ardışık sıkıştırmada özetin özeti ilk özeti silerdi.
            return [f"[kullanıcı] {message.content[:TRACE_SUMMARY_CHARS]}"]
        return [f"[kullanıcı] {excerpt}"]
    if message.role == "tool":
        # Başarı bilgisi mesajın kendisinde taşınır; metinden tahmin edilmez.
        flag = " ⟵ HATA" if message.ok is False else ""
        pay = message_chars * TRACE_ERROR_FACTOR if message.ok is False else message_chars
        return [f"[sonuç {message.name or ''}{flag}] {_sample(message.content, pay)}"]
    if message.role == "assistant":
        # Argüman kesme payı mesaj payıyla birlikte büyür: sabit 200 karakter,
        # denetçiye `write_file`'ın yalnızca yolunu gösterip ne yazdığını gizliyordu.
        described = [
            f"[araç çağrısı] {call.name}({call.arguments[:message_chars]})"
            for call in message.tool_calls
        ]
        if message.content:
            described.append(f"[asistan] {excerpt}")
        return described
    return []
