"""Refleksiyon — araç hatasından sonra modele yön veren not.

EK MODEL ÇAĞRISI YAPMAZ: yalnızca geçmişe kısa bir kullanıcı mesajı enjekte eder.
Amaç, modelin aynı hatalı çağrıyı körlemesine tekrarlamasını önlemektir; bu bedava
bir davranış düzeltmesidir.

`goal` kipinde daha ısrarcı bir varyant kullanılır: orada pes etmek yasaktır.
"""

from __future__ import annotations

import shlex
from typing import Literal

from ...core.tool_emulation import PAYLOAD_EXAMPLE, PAYLOAD_RULES, render_call
from ...core.types import Message

WORKSPACE_NOTE = (
    "[refleksiyon] Son araç çağrılarından en az biri HATA döndürdü. Kısaca ne yanlış "
    "gitti düşün ve FARKLI bir yaklaşım dene — aynı çağrıyı birebir tekrarlama. "
    "Gerekirse önce keşif yap (read_file / search_code), sonra hedefli düzelt."
)

STANDARD_NOTE = (
    "[refleksiyon] Son araç çağrılarından en az biri HATA döndürdü. Hatayı değerlendir; "
    "aynı başarısız çağrıyı körlemesine tekrarlama. Kullanıcının istediği ve izin verdiği "
    "kapsamda uygun gözlemle eksik bilgiyi edin, sonucu doğrula. Bir engel varsa açıkla."
)
DESKTOP_NOTE = (
    "[refleksiyon] Son araç çağrılarından en az biri HATA döndürdü. Hedef uygulama "
    "ve pencerenin güncel durumunu izinli masaüstü gözlemiyle doğrula. Eski veya belirsiz "
    "hedefe körlemesine eylem uygulama. Yalnız istenen işlem kapsamında ilerle; "
    "sonucu gözlemle doğrula. İzin veya kimlik engeli varsa açıkla."
)
RecoveryContext = Literal["workspace", "desktop", "observation"]


def recovery_context(*, required_effect: str | None, desktop: bool) -> RecoveryContext:
    """File-changing recovery requires this turn's affirmative workspace contract."""
    if required_effect == "workspace_mutation":
        return "workspace"
    return "desktop" if desktop else "observation"


PERSISTENT_NOTE = (
    "[refleksiyon] Son araç çağrısı HATA döndürdü. Pes etme: hatayı dikkatlice oku ve "
    "farklı bir yol, araç ya da parametre dene. Kendi başına aşamayacağın bir durumsa "
    "ask_user ile kullanıcıdan destek iste."
)

AUTO_CONTINUE_NOTE = (
    "[otomatik-devam] İşi yarım bıraktın gibi görünüyor. Niyet beyan etmek yerine ya bir "
    "araç çağırıp devam et ya da somut nihai teslimi ver. Zaten bittiyse tek cümleyle teyit et."
)


#: Aynı düzenleme aynı hatayla üst üste düşünce gönderilen not.
#
# Ölçüldü: `edit_file` beş kez üst üste "'old' metni dosyada bulunamadı" verdi.
# Model her seferinde DAHA DAR bir pencere okuyup aynı yaklaşımı tekrarladı ve
# turun tamamı bu döngüde yandı. Genel refleksiyon notu ("farklı bir yaklaşım
# dene") yetmiyor: model onu zaten "biraz daha oku" diye yorumluyor. Çıkış yolu
# ADIYLA gösterilmeli.
REPEATED_EDIT_NOTE = (
    "[düzenleme-döngüsü] Aynı dosyada {count} kez düzenleme denedin ve hepsi "
    "eşleşmeme hatasıyla düştü. Aynı yolu bir daha deneme; daha dar bir pencere "
    "okumak da işe yaramayacak.\n"
    "Şunlardan BİRİNİ yap:\n"
    "1) Dosyanın değiştireceğin bölümünü offset/limit ile TAM olarak oku ve "
    "'old' metnini o çıktıdan BİREBİR kopyala (satır numarası önekini bırakabilirsin).\n"
    "2) Değişecek yer birden çok parçaysa multi_edit kullan.\n"
    "3) Eşleşecek benzersiz bir metin bulamıyorsan dosyanın TAMAMINI okuyup "
    "write_file ile yeniden yaz — tamamını okuduysan bu yol açıktır.\n"
    "4) Hiçbiri mümkün değilse ne yapamadığını açıkça söyle ve dur."
)


def repeated_edit_note(count: int) -> Message:
    """Düzenleme döngüsünden çıkışı ADIYLA göster."""
    return Message("user", REPEATED_EDIT_NOTE.format(count=count), harness_note=True)


#: Turda şu ana kadar değiştirilen dosyaların KAYDI.
#
# Ölçüldü: model üç dosya oluşturdu ve kapanışta "herhangi bir değişiklik
# yapılmamıştır" dedi; başka bir koşuda dokunmadığı dosyayı "güncelledim" dedi.
# Model kendi işini takip edemiyor. Kayıt her mutasyon turundan sonra geçmişe
# eklenir — iddia değil olgu, ve nihai cevabı yazarken elinin altında olur.
CHANGE_LOG_NOTE = "[kayıt] Bu turda şu ana kadar DEĞİŞTİRDİĞİN dosyalar: {paths}"


def change_log_note(paths: tuple[str, ...]) -> Message:
    """Değişen dosyaları modele olgu olarak hatırlat."""
    return Message("user", CHANGE_LOG_NOTE.format(paths=", ".join(paths)), harness_note=True)


#: Görevdeki dosyaların hiçbiri çalışma dizininde bulunamadı.
#
# Ölçüldü: kullanıcı fusion'ı yanlış klasörde açtı; model dört dosyayı da
# bulamadı ve öz-denetim turunda GÖREVİ TERK EDİP kendine yeni iş uydurdu (o
# projenin README'sini okuyup "test paketini çalıştır" diye plan yazdı).
# Yapılamayan iş, uydurulacak iş değildir.
WRONG_WORKSPACE_NOTE = (
    "[yanlış-dizin] Görevde geçen dosyaların hiçbiri bu çalışma dizininde yok: "
    "{root}\n"
    "En olası açıklama, fusion'ın YANLIŞ KLASÖRDE açılmış olmasıdır. ŞUNU YAP: "
    "kullanıcıya bu dizinde aradığı dosyaların bulunmadığını, doğru proje "
    "dizininde çalıştırması gerektiğini söyle ve DUR.{oneri}\n"
    "Başka bir iş ARAMA ve UYDURMA: bu dizinde ne olduğunu keşfedip kendine yeni "
    "görev çıkarmak, kullanıcının istediği şey değildir."
)

#: Doğru dizin bulunduğunda nota eklenen somut çıkış yolu.
#
# Dizin DEĞİŞTİRİLMEZ, önerilir: kök kısıtı kullanıcının açtığı dizinin dışına
# çıkılmasın diye vardır ve "sanırım şunu kastettin" deyip başka bir projede
# dosya düzenlemeye başlamak kabul edilemez bir risktir. Karar kullanıcınındır.
_WORKSPACE_SUGGESTION = (
    "\nAradığın dosyalar şu dizinde duruyor: {path}\n"
    "Kullanıcıya bu komutu ver ve orada tekrar denemesini söyle:\n"
    "  cd {path} && fusion"
)


def wrong_workspace_note(root: str, suggestion: str = "") -> Message:
    """Yanlış çalışma dizini hipotezini modele bildir ve durmasını iste."""
    # Dizin adındaki `"`, `$`, `` ` `` kullanıcı komutu kopyalayınca yorumlanmasın (A3-25).
    oneri = _WORKSPACE_SUGGESTION.format(path=shlex.quote(suggestion)) if suggestion else ""
    return Message("user", WRONG_WORKSPACE_NOTE.format(root=root, oneri=oneri), harness_note=True)


def note(*, persistent: bool, context: RecoveryContext = "observation") -> Message:
    """Araç hatasından sonra görevin yetkili kapsamı içinde yön ver."""
    text = {"workspace": WORKSPACE_NOTE, "desktop": DESKTOP_NOTE}.get(context, STANDARD_NOTE)
    return Message("user", PERSISTENT_NOTE if persistent else text, harness_note=True)


def auto_continue_note() -> Message:
    return Message("user", AUTO_CONTINUE_NOTE, harness_note=True)


def keep_delivery(delivery: str, confirmation: str) -> str:
    """Otomatik-devam notuna verilen araçsız cevaptan sonra kullanıcıya gidecek metin.

    Teyit asıl tesliminden kısaysa teslim korunur; model notla yeni ve daha dolu bir
    teslim yazdıysa (ör. özet genişledi) o kullanılır.
    """
    if not delivery.strip():
        return confirmation
    return confirmation if len(confirmation.strip()) > len(delivery.strip()) else delivery


#: İlerlemesiz turlar birikince, turu kesmeden ÖNCE gönderilen not.
#
# Ölçüldü (28 Eylül, büyük proje görevi): model 13 dakika boyunca yalnız arama ve
# okuma yaptı, hiçbir görevi tamamlamadan "ilerleme yok" ile cevapsız kesildi.
# Bekleyen görev varken doğru hamle keşfi bırakıp ilk somut değişikliği yapmaktır.
WORKSPACE_STALL_RESCUE_NOTE = (
    "[ilerleme-yok] Son turlarda yeni bir şey öğrenmedin ve hiçbir dosyayı "
    "değiştirmedin. Aramayı bırak: elindeki bilgiyle görev listesindeki sıradaki "
    "maddenin İLK somut değişikliğini şimdi yap. Bir engel varsa onu tek cümleyle açıkla."
)


STALL_RESCUE_NOTE = (
    "[ilerleme-yok] Son turlarda yeni ilerleme doğrulanmadı. Aynı keşfi tekrarlama. "
    "Kullanıcının istediği kapsamda eksik kanıtı tamamla veya doğrulanmış sonucu sun. "
    "Bir engel varsa onu açıkla; yeni bir görev uydurma."
)
DESKTOP_STALL_RESCUE_NOTE = (
    "[ilerleme-yok] Son turlarda hedef uygulama üzerinde yeni ilerleme doğrulanmadı. "
    "Yalnız istenen masaüstü işlemi için güncel hedef uygulama/pencere durumunu gözle. "
    "Kimlik ve izin doğrulanıyorsa sıradaki yetkili işlemi yap ve gerçek sonucu doğrula. "
    "Aynı başarısız eylemi körlemesine tekrarlama; engel varsa açıkla."
)


def stall_rescue_note(*, context: RecoveryContext = "observation") -> Message:
    text = {"workspace": WORKSPACE_STALL_RESCUE_NOTE, "desktop": DESKTOP_STALL_RESCUE_NOTE}.get(
        context, STALL_RESCUE_NOTE
    )
    return Message("user", text, harness_note=True)


#: Yanıt bütünlüğü sınıfına göre gönderilecek not.
#
# Üç kayıp biçimi farklı hamle ister: kesilmiş yanıtta yapılan işi koruyup devam
# etmek, kapanmamış blokta yalnız eksik bloğu tamamlatmak, boş yanıtta isteği
# sadeleştirip tek adıma indirmek gerekir. Üçünü aynı nota bağlamak, ya yapılan işi
# çöpe atıyor ya da modele yanlış şeyi düzelttiriyordu (ölçüldü, web koşuları).
_INTEGRITY_NOTES: dict[str, str] = {
    "truncated": (
        "[taşıma] Yanıtın çıktı sınırında kesildi. Baştan başlama: kaldığın yerden "
        "devam et ve yalnız eksik kalan kısmı üret."
    ),
    "unclosed_block": (
        "[taşıma] Bir araç bloğu açıldı ama kapatılmadı; çağrı okunamadı. Açıklama "
        "yazma, yalnız o bloğu sözleşmeye uygun biçimde TAM olarak yeniden üret."
    ),
    "empty": (
        "[taşıma] Yanıt boş geldi. İsteği tek ve kısa bir adıma indir; uzun bir "
        "plan yerine yalnız sıradaki tek araç çağrısını yaz."
    ),
}


def integrity_note(integrity: object) -> Message | None:
    """Bütünlük sınıfına ait notu üret; sağlam yanıtta `None`."""
    metin = _INTEGRITY_NOTES.get(str(getattr(integrity, "value", integrity)))
    return Message("user", metin, harness_note=True) if metin else None


#: Boş cevap sonrası modele verilen dürtü. Suçlayıcı değil yönlendirici: model
#: cevabı neden düşürdüğünü bilmiyor, tekrar denemesi isteniyor.
EMPTY_RESPONSE_NOTE = (
    "Boş bir cevap döndürdün. Göreve devam et: ya bir araç çağır ya da "
    "yaptıklarını özetleyen bir cevap yaz."
)


def empty_response_note() -> Message:
    """Boş cevaptan sonra enjekte edilen kullanıcı notu."""
    return Message("user", EMPTY_RESPONSE_NOTE, harness_note=True)


_EFFECT_LABELS = {
    "tool_action": "istenen çalışma (başarılı bir araç işlemi)",
    "git_push": "Git uzak deposunu güncelleme (başarılı bir `git push`)",
    "git_commit": "Git commit oluşturma (başarılı bir `git commit`)",
    "shell_action": "istenen komut/sistem işlemi (başarılı `run_shell`)",
    "workspace_mutation": "çalışma alanını değiştirme (başarılı değiştirici araç)",
    "web_lookup": "web araştırması (başarılı `web_search` veya `web_fetch`)",
    "workspace_read": "çalışma alanını inceleme (başarılı okuma/arama aracı)",
}


def tool_evidence_required_note(effect: str | None, attempt: int = 1) -> Message:
    """Model eylem sözü verdi ama gerçek araç çalıştırmadıysa onu araca zorla.

    İlk uyarı kanonik çağrıyı gösterir. Küçük modeller bunu yok sayıp yine niyet
    yazabiliyor (20 Ekim: 9B model iki kez "betiği çalıştıracağım" dedi, hiç araç
    çağırmadı); sonraki uyarılar açıklamayı yasaklar ve ilk adımı somut söyler.
    """

    label = _EFFECT_LABELS.get(effect or "", "kullanıcının istediği gerçek işlem")
    if effect == "web_scope":
        return Message(
            "user",
            "FUSION_NOT: Kullanıcı okuma kapsamını sınırladı; bu sınır sayfanın "
            "diğer içeriği hakkında kesin çıkarıma izin vermez. Tam metin okumasına veya yeni "
            "adrese geçme. Yalnız izinli gözlemi bildir ve doğrulanamayan kısmı açıkça söyle.",
            harness_note=True,
        )
    if effect == "web_content":
        return Message(
            "user",
            "FUSION_NOT: Sayfa içeriği için kaynak okuması doğrulanmadı. Etkileşimli, alt ağaç, "
            "derinlik sınırlı veya kırpılmış gözlem metnin yokluğunu kanıtlamaz. Yalnız "
            "kullanıcının yetkilendirdiği mevcut sayfada get_page_text ile tam görünür metni "
            "oku; page=1 ve has_more=false olmayan bir parça tüm belgeyi kanıtlamaz. "
            "Başka adrese gitme, kapsam dışı metin veya kontroller üzerinde işlem yapma.",
            harness_note=True,
        )
    if effect == "web_lookup":
        last = (
            " Bu son deneme; kanıt yoksa güncelliğin doğrulanamadığını bildir."
            if attempt >= 3
            else ""
        )
        return Message(
            "user",
            "[eylem-kanıtı-zorunlu] Bu araştırma için yeterli kaynak okuması doğrulanmadı. "
            "Kullanıcının belirttiği URL'leri web_fetch ile oku; URL yoksa web_search ile "
            "ilgili birincil kaynağı bul ve oku. Başka bir sayfayı okumuş olmak istenen "
            "kaynağı doğrulamaz. Erişim tarihi ile yayın tarihini ayır; eski bir sayfayı "
            "bugün çekmek bilginin güncel olduğunu kanıtlamaz. "
            "Erişim yoksa bilgiyi tahmin etme ve yapılmış gibi sunma." + last,
            harness_note=True,
        )
    if effect == "workspace_read":
        return Message(
            "user",
            "[eylem-kanıtı-zorunlu] İstenen çalışma alanı incelemesi henüz doğrulanmadı. "
            "İlgili yolu list_dir, read_file veya search_code ile incele ve bulguyu bildir. "
            "Bu bir okuma görevi; kanıt üretmek için dosya değiştirme.",
            harness_note=True,
        )
    if attempt >= 2:
        son = " Bu SON uyarı: bundan sonra tur başarısız kapanır." if attempt >= 3 else ""
        return Message(
            "user",
            f"[eylem-kanıtı-zorunlu] Hâlâ {label} için araç çağırmadın.{son} "
            "Cevabında YALNIZCA bir araç çağrısı olsun, açıklama yazma. Nereden "
            "başlayacağını bilmiyorsan ilk adım olarak list_dir (path='.') ile klasörü "
            "listele, sonra read_file ya da search_code ile ilerle. Bilgi eksikse "
            "ask_user kullan.",
            harness_note=True,
        )
    return Message(
        "user",
        "[eylem-kanıtı-zorunlu] Kullanıcı gerçek bir işlem istedi fakat henüz "
        f"{label} için başarılı bir araç sonucu yok. 'Kontrol ediyorum', 'yapıyorum', "
        "'güncelliyorum' gibi niyet cümleleriyle bitirme. Şimdi uygun aracı kanonik "
        "biçimde çağır:\n"
        f"{render_call({'name': 'run_shell', 'arguments': {'command': '…'}})}\n"
        "İşlem için bilgi/onay eksikse ask_user kullan. Aracı kullanamıyorsan işlemin "
        "yapılmadığını açıkça söyle; yapılmış gibi davranma.",
        harness_note=True,
    )


def unverified_action_message(effect: str | None) -> str:
    """İki araçsız denemeden sonra kullanıcıya dürüst ve kesin sonuç ver."""

    if effect == "web_scope":
        return (
            "Sayfa içeriği için kaynak okuması doğrulanmadı: izin verilen kısmi gözlem "
            "bu çıkarım için yeterli değil. Okuma kapsamı genişletilmedi."
        )
    if effect == "web_content":
        return (
            "İşlem tamamlanmadı: sayfa içeriği için kaynak okuması doğrulanmadı. "
            "Eldeki gözlem kısmi; görünmeyen metnin sayfada bulunmadığını söyleyemem."
        )
    if effect == "web_lookup":
        return (
            "İşlem tamamlanmadı: araştırma için gerekli kaynak okuması doğrulanmadı. "
            "Bilgi kaynağa dayanarak doğrulanmış kabul edilemez."
        )
    label = _EFFECT_LABELS.get(effect or "", "istenen işlem")
    return (
        f"İşlem tamamlanmadı: {label} için başarılı bir araç çağrısı doğrulanamadı. "
        "Herhangi bir değişiklik yapılmış veya uzak sistem güncellenmiş kabul edilmemelidir."
    )


def unverified_action_reply(effect: str | None, reply: str) -> str:
    """Kanıtsız iddia uyarısını ÖNE koy, modelin cevabını SİLME (A2-22).

    Ölçüldü (30 Ekim): kapı cevabı tamamen sabit bir mesajla değiştiriyordu; bir
    komutu/akışı AÇIKLAYAN meşru cevap ("git push yapınca ... olur") yanlış-pozitifle
    kayboluyordu. Uyarı başta kalır (kullanıcı önce onu görür), cevap "doğrulanmadı"
    etiketiyle altında korunur; geçmişe de aynı metin gider, iddia olgu gibi taşınmaz.
    """
    warning = unverified_action_message(effect)
    kept = reply.strip()
    if not kept:
        return warning
    return f"{warning}\n\nModelin cevabı (kanıtsız, doğrulanmadı):\n{kept}"


def tool_contract_repair_note(detail: str) -> Message:
    """Modele bozuk çağrıyı düzeltmesi için TEK ve kesin bir şans ver.

    Örnek ve kurallar `core.tool_emulation`'dan gelir: sözleşme iki yerde ayrı ayrı
    yazılıydı ve her düzeltmede ikisinin elle senkronlanması gerekiyordu.
    """
    return Message(
        "user",
        "[tool-contract-repair] Önceki araç çağrın geçersizdi. "
        f"Hata: {detail}\n"
        "Yalnızca bir kez düzelt.\n\n"
        "Kısa çağrı örneği:\n"
        f"{render_call({'name': 'read_file', 'arguments': {'path': 'src/app.py'}})}\n\n"
        "Çok satırlı kodu JSON stringine koyma; payload kullan:\n"
        f"{PAYLOAD_EXAMPLE}\n\n" + "\n".join(PAYLOAD_RULES) + "\nAynı geçersiz çağrıyı tekrarlama. "
        "Düzeltemiyorsan işlemin tamamlanmadığını açıkça söyle.",
        harness_note=True,
    )


def verification_action_required_note() -> Message:
    """Blocking verification correction'ın araçsız kapanmasını engelle."""

    return Message(
        "user",
        "Henüz gerçek bir kod düzeltmesi yapmadın. Blocking doğrulama sorunları "
        "çözülmedi. Doğrulama/test komutunu tekrar ÇALIŞTIRMA; sonucu zaten biliyoruz "
        "ve kapı kod değişikliğinden sonra otomatik tekrar çalışacak. İlgili dosyayı "
        "gerekirse read_file/search_code ile incele. Mevcut dosyada hedefli düzeltme "
        "için edit_file(path, old, new) kullan; yalnız uygun durumda write_file "
        "kullan. Mutlaka bir DEĞİŞTİRİCİ aracı gerçekten çağır. "
        "run_shell ile yalnız doğrulamayı tekrar etmek çözüm değildir. Araç çağrısını "
        "düz metin JSON veya kod bloğu olarak yazma; gerçekten çalıştır.",
        # Her diğer not fabrikası gibi harness notu: kullanıcı sözü sayılmaz (A3-24).
        harness_note=True,
    )


def refusal_note(tool_names: list[str]) -> Message:
    """Araç varken kalıp ret verildiğinde modele bir kez araçlarını hatırlat."""
    araclar = ", ".join(tool_names[:8])
    return Message(
        "user",
        "Bu bir ret cevabı gibi görünüyor, ama bu görev için araçların var "
        f"({araclar}). Görevi araçlarla yapmaya başla. Gerçekten yapılamıyorsa hangi "
        "aracı denediğini ve neden olmadığını somut olarak yaz.",
        harness_note=True,
    )


def unsupported_claim_note() -> Message:
    """Modelin kendi iddiasını kullanıcı adına bir iş emrine dönüştürme."""
    return Message(
        "user",
        "[kanıtsız-işlem-beyanı] Son yanıtındaki işlem iddiası bu turun araç "
        "sonuçlarıyla doğrulanmadı. İddiayı geri al ve gerçek durumu açıkla. "
        "Sırf bu iddiayı kanıtlamak için yeni bir değişiklik yapma. "
        "Yalnızca kullanıcının gerçekten istediği ve izin verdiği işlemleri "
        "uygun araçlarla yapabilirsin; öneriyi, geçmiş işi ve bu turda yapılan "
        "işlemi açıkça ayır.",
        harness_note=True,
    )
