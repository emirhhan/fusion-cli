"""Ajan araç sözleşmesi ve onarım mesajları; döngü durumundan bağımsız saf yardımcılar."""

from __future__ import annotations

import json
import re

from ...core.constants import TOOL_CALL_DUPLICATE_PREFIX
from ...core.verification import VerificationResult
from ...tools import ToolRegistry
from ...tools.emulation import render_tool_example


def _encode_arguments(args: dict[str, object]) -> str:
    """Argümanları tekrar tespiti için KARARLI bir metne çevir.

    Anahtar sırası sabitlenir: aynı çağrının farklı sırayla gelmesi onu yeni bir
    çağrı yapmaz. Serileştirilemeyen bir değer varsa `repr` yeterlidir — burada
    amaç eşitlik karşılaştırması, yeniden üretilebilir bir kayıt değil.
    """
    try:
        return json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(args)


def _parse_arguments_checked(raw: str) -> tuple[dict[str, object], str | None]:
    """Ham argümanları ayrıştır; bozuk JSON kanıtını SİLMEDEN.

    Hatayı yutup boş sözlük döndürmek, modele "argümanların boştu" demek olurdu;
    oysa sorun JSON'un kendisidir ve model bunu bilmeden düzeltemez.
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        # Model geçerli nesnenin ARKASINA artık bırakabiliyor (ikinci nesne, kapanış
        # çiti, düz metin): "Extra data". İlk tam nesne açıkça okunabiliyorsa çağrı
        # yapılır — aksi hâlde doğru argümanlar yüzünden tur "zorunlu alan eksik"
        # onarım döngüsüne giriyordu (18 Ekim 2026, web_search).
        ilk = _first_json_object(raw) if isinstance(raw, str) else None
        if ilk is None:
            return {}, f"arguments geçerli JSON olmalı ({error})"
        return ilk, None
    if not isinstance(parsed, dict):
        return {}, "arguments bir JSON nesnesi olmalı"
    return parsed, None


def _first_json_object(raw: str) -> dict[str, object] | None:
    """Metnin başındaki ilk TAM JSON nesnesini döndür; yoksa None."""
    metin = raw.lstrip()
    if not metin.startswith("{"):
        return None
    try:
        nesne, _son = json.JSONDecoder().raw_decode(metin)
    except (json.JSONDecodeError, ValueError):
        return None
    return nesne if isinstance(nesne, dict) else None


_SHELL_FRAME = re.compile(r"^\(çıkış kodu -?\d+\)$|^\[stderr\]$")


def _failure_signature(output: str) -> str:
    """Hata metnini karşılaştırılabilir bir imzaya indir.

    İlk satır alınır: araçlar çözüm önerilerini sonraki satırlara yazar ve o
    öneriler aynı hatada bile değişebilir. Yol/ad gibi ayrıntılar İMZANIN
    PARÇASIDIR — farklı dosyada aynı hata farklı iştir, yinelenme sayılmaz.
    """
    # Kabuk çıktısı hep "(çıkış kodu N)" ile başlar: o satır imza olsaydı birbiriyle
    # ilgisiz her kabuk hatası "aynı hata" sayılırdı. Asıl hata satırı alınır.
    satirlar = [
        satir.strip()
        for satir in output.strip().splitlines()
        if satir.strip() and not _SHELL_FRAME.match(satir.strip())
    ]
    return satirlar[0] if satirlar else output.strip()


def _duplicate_call_message() -> str:
    """Tekrarlanan çağrıda modele verilen rehberlik.

    Ölçülen hata: mesaj yalnız DOSYA araçlarını sayıyordu. MCP ya da başka bir
    dış araçla çalışan model bu listeden hiçbirini uygulayamıyor ve engellenen
    aracı tümden yasaklanmış sanıyordu. Gerçek bir Godot turunda `add_node`
    yolu `res://` ekiyle reddedildi; doğru düzeltme AYNI aracı ek olmadan
    çağırmaktı, ama mesaj argüman değiştirmeyi hiç önermiyordu.

    Bu yüzden ilk öneri araç-bağımsızdır: ARGÜMANI değiştir. Dosya araçları
    yalnızca örnek olarak kalır.
    """
    return (
        f"{TOOL_CALL_DUPLICATE_PREFIX} Bu çağrıyı aynı argümanlarla ZATEN yaptın ve çalışma "
        "alanında o zamandan beri ilgili bir değişiklik olmadı. Fusion çağrıyı "
        "çalıştırmadı — sonucu zaten elinde. Araç YASAK DEĞİL; yasak olan aynı "
        "çağrıyı aynı argümanlarla tekrarlamak.\n"
        "Şunlardan BİRİNİ yap:\n"
        "1) Aynı aracı FARKLI ARGÜMANLARLA çağır. Önceki hata bir yol/biçim "
        "sorunuysa yolu değiştir (ör. 'res://' ekini kaldır ya da ekle, göreli "
        "yol yerine tam yol ver).\n"
        "2) Aynı işi yapan BAŞKA bir aracı dene.\n"
        "3) Dosya işi ise: yeni dosyada write_file, mevcut dosyada edit_file, "
        "başka bir dosyayı read_file ile oku.\n"
        "4) Eksik bilgi varsa ask_user ile sor.\n"
        "5) İş bittiyse sonucu söyle."
    )


def _is_tool_contract_error(detail: str | None) -> bool:
    return bool(detail and detail.startswith("TOOL_CALL_"))


def _tool_contract_failure(
    name: str,
    errors: list[str],
    function_schema: object,
    *,
    registry: ToolRegistry | None = None,
) -> str:
    """Sözleşme hatasını, ÖRNEĞİ hatanın işaret ettiği araçtan vererek bildir.

    Ölçüldü (13 Eylül, Godot koşusu): `write_file` mevcut dosyada reddedildi ve
    hata "replace_range kullan" dedi — ama örnek yine `write_file` çağrısıydı.
    Model örneği izleyip aynı çağrıyı tekrarladı, adım bütçesi doldu ve oyun
    yarım kaldı. Hata bir aracı önerirken başka bir aracın örneğini göstermek,
    öneriyi geri almaktır.
    """
    lines = ["TOOL_CALL_INVALID", f"tool: {name}", "errors:"]
    lines.extend(f"- {error}" for error in errors)
    onerilen = _suggested_tool_schema(name, errors, registry)
    if onerilen is not None:
        lines.append("valid_example:")
        lines.append(render_tool_example(onerilen))
    elif isinstance(function_schema, dict):
        lines.append("valid_example:")
        lines.append(render_tool_example(function_schema))
    return "\n".join(lines)


def _suggested_tool_schema(
    name: str, errors: list[str], registry: ToolRegistry | None
) -> dict[str, object] | None:
    """Hata metninde ADIYLA önerilen BAŞKA aracın şeması; yoksa None.

    Metinde birden çok araç anılıyorsa EN SONA yazılan seçilir: öneriler sıra
    halinde yazılıyor ("önce read_file ile gör, sonra edit_file ile gönder")
    ve modelin yanlış yaptığı adım zincirin sonundaki YAZMA adımıdır.
    """
    if registry is None:
        return None
    metin = " ".join(errors)
    sirali = sorted(
        ((metin.rfind(aday), aday) for aday in registry.names() if aday != name),
        reverse=True,
    )
    for konum, aday in sirali:
        if konum < 0:
            break
        tool = registry.get(aday)
        if tool is None:
            continue
        schema = tool.schema().get("function")
        if isinstance(schema, dict):
            return schema
    return None


def _tool_contract_abort_message(detail: str) -> str:
    return (
        "TOOL_CALL_ABORTED: Araç sözleşmesi düzeltilemedi veya aynı çağrı tekrarlandı. "
        "Fusion güvenlik için bu turu sonlandırdı; işlem tamamlanmış kabul edilmemelidir.\n"
        + detail
    )


CORRECTION_NOTE_PREFIX = "[Fusion doğrulama]"


def _correction_task(feedback: str) -> str:
    """Öz-denetim düzeltmesi için KISA not üret.

    Ölçüldü: eski talimat kullanıcının görevini BAŞTAN anlatıyordu
    ("Kullanıcının görevi şuydu: …") ve model bunu SAHTE bir yeni kullanıcı
    mesajı sanıp "iş henüz verilmedi, ne yapmamı istiyorsunuz" diyerek turu
    bitiriyordu — birinci turda yapılmış işi de götürerek. Tek konuşma geçmişi
    ilkesi burada da geçerlidir: görev zaten paylaşılan geçmişte duruyor,
    tekrar anlatmaya gerek yok; yalnız hangi sorunun düzeltileceği söylenir.
    """
    return (
        f"{CORRECTION_NOTE_PREFIX} Bir öz-denetim şu sorunu işaret etti. Gerekiyorsa "
        "düzelt; haklı değilsen kısaca neden sorun olmadığını açıkla.\n\n"
        f"{feedback}"
    )


def _verification_correction_task(verification: VerificationResult) -> str:
    # Bulgu yoksa özet tek başına talimat olur: elde bundan fazlası yok, ama
    # "doğrulama düştü" bilgisi bile modele hiçbir şey söylememekten iyidir.
    details = verification.findings or ((verification.summary,) if verification.summary else ())
    findings = "\n".join(f"- {finding}" for finding in details)
    # Görev TEKRAR EDİLMEZ: paylaşılan geçmiş zaten taşıyor. Talimat sahte bir
    # kullanıcı mesajı gibi davranıp modelin "görev yeniden mi verildi" sanmasına
    # yol açmasın diye Fusion'ın kendi sesiyle (`CORRECTION_NOTE_PREFIX`) işaretlenir.
    return (
        f"{CORRECTION_NOTE_PREFIX} Doğrulama kapısı üretilen çıktıda şu somut "
        "sorunları buldu. Bunları gerçek kod değişiklikleriyle düzelt. "
        "Doğrulama/test komutunu şimdi TEKRAR ÇALIŞTIRMA; kapı sen değişiklik "
        "yaptıktan sonra otomatik olarak yeniden çalışacak. Gerekirse ilgili dosyayı "
        "oku, fakat ardından en az bir gerçek değiştirici araç çağır "
        "(edit_file/write_file vb.). Salt açıklama, plan, JSON veya kod bloğu "
        "düzeltme değildir. Düzeltemeyeceğin varsa nedenini tek cümleyle yaz. "
        f"\n\n{findings}"
    )
