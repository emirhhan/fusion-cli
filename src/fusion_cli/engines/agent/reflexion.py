"""Refleksiyon — araç hatasından sonra modele yön veren not.

EK MODEL ÇAĞRISI YAPMAZ: yalnızca geçmişe kısa bir kullanıcı mesajı enjekte eder.
Amaç, modelin aynı hatalı çağrıyı körlemesine tekrarlamasını önlemektir; bu bedava
bir davranış düzeltmesidir.

`goal` kipinde daha ısrarcı bir varyant kullanılır: orada pes etmek yasaktır.
"""

from __future__ import annotations

import re

from ...core.tool_emulation import PAYLOAD_EXAMPLE, PAYLOAD_RULES, render_call
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


#: Model hiç araç çağırmadan turu kapatmaya çalıştığında gönderilen not.
#
# Ölçüldü: model "somut bir görev almadım, dizin içeriğini listeliyorum" deyip
# hiçbir araç çağırmadan üç tur döndü ve tur başarılı sayıldı. Not, görevi
# yeniden okumasını ve TEK bir somut adım atmasını ister — genel bir "devam et"
# dürtüsü burada işe yaramıyor, çünkü model işi yarım bırakmış değil hiç
# başlamamıştır.
NEVER_ACTED_NOTE = (
    "[hic-arac-yok] Bu turda hiçbir araç çağırmadın ve hiçbir şey değişmedi. "
    "Görev promptun sonundaki 'GÖREV (yapılacak iş budur)' bloğunda yazılı — onu "
    "yeniden oku. Şimdi TEK bir somut adım at: ilgili dosyayı read_file ile aç ya "
    "da değişikliği edit_file ile yap. Görevi gerçekten anlamadıysan ask_user "
    "çağır; düzyazıyla 'görev belirtilmedi' deyip durma."
)


ASKED_INSTEAD_OF_ACTING_NOTE = (
    "[otomatik-devam] Hiçbir şey değiştirmeden turu bir soruyla bitirdin. Kullanıcı "
    "görevini zaten verdi; ne yapman gerektiğini ona geri sorma. Elindeki araçlarla "
    "cevabını bulabiliyorsan bul ve devam et. Soru gerçekten kullanıcının kararıysa "
    "(yıkıcı işlem, birbirini dışlayan iki gereksinim) ask_user aracını çağır — "
    "düzyazıyla sorup durma."
)


#: Modelin okumaktan çıkıp değiştirmeye geçmesini isteyen not.
#
# Ölçüldü (Gemini web, aynı görev üç koşu): model dizin listeledi, dosya okudu,
# başka dizin listeledi, başka dosya okudu… ve tur bütçesi keşifle doldu. Tek bir
# satır bile değişmedi. Model tembel değildi — hiçbir yerde "yeterince gördün,
# şimdi yap" diyen bir sinyal yoktu ve keşif kendi kendini besliyordu.
#
# Kapı tur SONUNDA değil ORTASINDA konuşur: sonda söylemek, bütçe zaten bittiği
# için işe yaramıyordu.
ENOUGH_EXPLORING_NOTE = (
    "[dur-ve-yap] {rounds} turdur yalnızca okuyorsun ve tek bir değişiklik "
    "yapmadın. Keşif yeterli. ŞİMDİ somut değişikliği yap: değiştireceğin ilk "
    "dosyayı seç ve edit_file / write_file çağır. Yeni dosya KEŞFETME; ama "
    "değiştireceğin dosyayı okumak keşif değildir — 'old' metnini tutturmak için "
    "onu okumak serbesttir ve gerekirse yapmalısın. Hangi dosyayı değiştireceğini "
    "bilmiyorsan bunu açıkça söyle ve dur."
)


def enough_exploring_note(rounds: int) -> Message:
    """Okumaktan yazmaya geçir."""
    return Message("user", ENOUGH_EXPLORING_NOTE.format(rounds=rounds), harness_note=True)


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
    '  cd "{path}" && fusion'
)


def wrong_workspace_note(root: str, suggestion: str = "") -> Message:
    """Yanlış çalışma dizini hipotezini modele bildir ve durmasını iste."""
    oneri = _WORKSPACE_SUGGESTION.format(path=suggestion) if suggestion else ""
    return Message("user", WRONG_WORKSPACE_NOTE.format(root=root, oneri=oneri), harness_note=True)


def note(*, persistent: bool) -> Message:
    """Araç hatasından sonra enjekte edilecek refleksiyon mesajı."""
    return Message("user", PERSISTENT_NOTE if persistent else STANDARD_NOTE, harness_note=True)


def auto_continue_note() -> Message:
    return Message("user", AUTO_CONTINUE_NOTE, harness_note=True)


def never_acted_note() -> Message:
    """Hiç araç çağırmadan turu kapatan modele TEK bir somut adım attır."""
    return Message("user", NEVER_ACTED_NOTE, harness_note=True)


def asked_instead_of_acting_note() -> Message:
    return Message("user", ASKED_INSTEAD_OF_ACTING_NOTE, harness_note=True)


def ends_with_question(final_text: str) -> bool:
    """Cevap kullanıcıya sorulan bir soruyla mı bitiyor?

    Ölçüt DİL DEĞİL noktalamadır: soru işareti Türkçede de İngilizcede de aynıdır,
    oysa "ne yapmamı istersiniz" kalıbını tanımaya çalışmak dile ve ifadeye bağımlı
    olurdu (bkz. `loop._stopped_without_acting` — duyuru metni bilinçli olarak
    dilsel yolla tanınmaz).

    Kapanış cümlesindeki soru işaretine bakılır, metnin herhangi bir yerindekine
    değil: gövdesinde retorik soru geçen dolu dolu bir teslim, soru sorarak
    bitirilmiş bir tur değildir.
    """
    return final_text.rstrip().endswith("?")


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
    return Message("user", EMPTY_RESPONSE_NOTE, harness_note=True)


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
        "'güncelliyorum' gibi niyet cümleleriyle bitirme. Şimdi uygun aracı kanonik "
        "biçimde çağır:\n"
        f"{render_call({'name': 'run_shell', 'arguments': {'command': '…'}})}\n"
        "İşlem için bilgi/onay eksikse ask_user kullan. Aracı kullanamıyorsan işlemin "
        "yapılmadığını açıkça söyle; yapılmış gibi davranma.",
        harness_note=True,
    )


def unverified_action_message(effect: str | None) -> str:
    """İki araçsız denemeden sonra kullanıcıya dürüst ve kesin sonuç ver."""

    label = _EFFECT_LABELS.get(effect or "", "istenen işlem")
    return (
        f"İşlem tamamlanmadı: {label} için başarılı bir araç çağrısı doğrulanamadı. "
        "Herhangi bir değişiklik yapılmış veya uzak sistem güncellenmiş kabul edilmemelidir."
    )


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
        "için replace_range(path, start_line, end_line, new) kullan; yalnız uygun "
        "durumda write_file kullan. Mutlaka bir DEĞİŞTİRİCİ aracı gerçekten çağır. "
        "run_shell ile yalnız doğrulamayı tekrar etmek çözüm değildir. Araç çağrısını "
        "düz metin JSON veya kod bloğu olarak yazma; gerçekten çalıştır.",
    )
