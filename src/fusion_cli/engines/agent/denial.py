"""Onay reddi ve onay alınamama metinleri — tek yer.

`loop.py`den taşındı: bu konudaki tüm sabitler ve gerekçeleri burada toplanır,
`loop.py` bir metin deposu olarak şişmez (RULES.md "Dosya Organizasyonu").

İKİ FARKLI durum birbirinden kesin çizgiyle ayrılır — ölçülen hata tam bu ikisinin
karıştırılmasıydı:

    DENIED       Kullanıcıya SORULDU ve HAYIR dedi. Tur burada durur; model bir
                 daha çağrılmaz, kullanıcıya "nasıl devam edeyim?" diye sorulur.
    UNAVAILABLE  Oturum etkileşimsiz olduğu için kimseye SORULAMADI. Tur SÜRER;
                 modelden onay gerektirmeyen bir yol denemesi istenir.

Eskiden ikisi TEK bir mesajla ("kullanıcı reddetmiş ya da oturum etkileşimsiz
olabilir") karşılanıyor ve her ikisinde de tur aynı şekilde sürüyordu. Canlı bir
turda kullanıcı GERÇEKTEN "hayır" dedi; model bunu görmezden gelip aynı işi başka
bir yoldan yapmaya çalıştı — kullanıcının kararı bir sonraki adımda yok sayıldı.
"""

from __future__ import annotations

#: DENIED sonrası kullanıcıya sorulan nihai cevap. `{tool}` reddedilen aracın adı.
#:
#: Tur burada BİTER — `loop._drive` bunu gördüğünde modeli bir daha ÇAĞIRMADAN
#: döner. Kullanıcının "hayır" dediği bir işlemi model başka bir yoldan yine de
#: yapmaya çalışırsa kullanıcının kararı yok sayılmış olur; doğru davranış durup
#: sormaktır.
DENIAL_STOP_ANSWER = (
    "`{tool}` çağrısını onaylamadınız; tur burada durduruldu. Nasıl devam edeyim?"
)

#: Reddedilen çağrının kendi tool-sonucu mesajı (konuşma geçmişine yazılır).
#:
#: Kısa tutulur: model bu turda BİR DAHA çağrılmayacağı için uzun bir gerekçeye
#: gerek yok — o, `DENIAL_STOP_ANSWER` ile zaten kullanıcıya söylenir. Bu metin
#: yalnızca geçmişte iz bırakır: sonraki bir kullanıcı turu ya da paylaşılan plan
#: geçmişi neyin olduğunu buradan okuyabilmelidir.
DENIED_TOOL_RESULT = "Kullanıcı bu işlemi reddetti; tur bu adımda durduruldu."

#: Aynı model yanıtındaki DENIED'dan SONRA gelen, artık hiç ÇALIŞTIRILMAYAN kalan
#: çağrılar için.
#:
#: API sağlayıcıları her `tool_call`'a karşılık bir sonuç mesajı ister; çağrı hiç
#: çalıştırılmasa da eşleşen bir "atlandı" mesajı gönderilmezse sağlayıcı isteğin
#: tamamını (çağrı/sonuç sayısı uyuşmadığı için) reddeder.
SKIPPED_TOOL_RESULT = (
    "Bu turda önceki bir işlem reddedildiği için tur durduruldu; bu çağrı hiç "
    "çalıştırılmadı."
)

#: Onay SORULAMADI (oturum etkileşimsiz: TTY yok, boru hattı, CI). Kullanıcının
#: reddiyle KARIŞTIRILMAMALI — burada tur SÜRER, modelden onay gerektirmeyen bir
#: yol denemesi istenir.
#:
#: Son cümle (UYDURMA UYARISI) ölçülen bir hatadan gelir: atlanan adım gerçek veri
#: getirecekti (ör. `git clone` sonrası dosya okuma); model adımı atladığını
#: metinde kabul etti ama ÇIKTI DOSYASINA yine de ezberden "gerçek" görünen
#: değerler yazdı — kullanıcı çıktıyı kaynağa dayalı sandı. Adımı atladığını
#: söylemek tek başına yeterli değildir; bu satır uydurmayı da ayrıca yasaklar.
APPROVAL_UNAVAILABLE_MESSAGE = (
    "Bu işlem için onay alınamadı — oturum etkileşimsiz olduğu için kimseye "
    "sorulamadı. Onay GEREKTİRMEYEN bir yol dene (dosya araçları onay istemez); "
    "mümkün değilse bu adımı neden atladığını açıkça yaz. Bu adımın getireceği "
    "veriyi (dosya içeriği, sayı, açıklama…) ASLA ezberden ya da tahminle üretip "
    "teslim ettiğin dosyaya/cevaba yazma — adımı atladığını söylemek yeterli "
    "değildir, UYDURULMUŞ değeri de yazmamalısın."
)
