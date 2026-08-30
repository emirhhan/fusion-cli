# CLAUDE.md

- Bu dosya her mesajda okunur ve yönlendiricidir.
- Kod ve karar vermeden önce [RULES.md](RULES.md) okunur — mimari, isimlendirme ve proje kuralları oradadır.
- Bu dosyalarda yazmayan bir şey kendi başına varsayılmaz, kullanıcıya sorulur.

## Projenin Amacı

- Bu proje, katmanlı, generic ve test edilebilir bir kodlama asistanıdır.
- Ürünün kimliği değişmez: ücretsiz LLM'lerle çalışan, iki motorlu (agent + fusion), öz-öğrenen, terminalde yaşayan bir kodlama asistanı.
- Tek-kullanımlık çözümler, kopyala-yapıştır tekrarlar ve tek dosyaya yığılmış sorumluluklar yazılmaz; kod merkezi yapıya bağlanır (RULES.md "Genel Tasarım" ve "Katman Sınırları").

## Geliştirme Akışı

- Büyük geliştirmeler her zaman **faz faz** planlanır; faz planı onaylanmadan kod yazılmaz.
- Her faz sonunda kalite kapısı çalıştırılır: `ruff check` + `mypy` + `pytest`. Üçü de temizse commit atılır, ancak ondan sonra bir sonraki faza geçilir.
- Bir faz yarım bırakılmaz; kapsam büyürse faz bölünür, kapsam sessizce genişletilmez.
- Bir özellik eklenirken testi de aynı fazda yazılır; testsiz modül "bitti" sayılmaz.
- Sabitler (timeout, eşik, limit, model kimliği) uydurulmaz; değeri gerekçesiyle konuşulur.
- Sırada olmayan modüle, iş gerektirmedikçe dokunulmaz.

## Dil

- Kod içi her şey Türkçe kalır: docstring, yorum, log, hata mesajı ve kullanıcıya görünen tüm CLI metinleri Türkçe yazılır.
- Tanımlayıcılar (modül, sınıf, fonksiyon, değişken adları) Python ekosistem uyumu için İngilizce ve PEP 8'e uygun yazılır.
- Detay: RULES.md "Dil".

## Sırlar

Bu bölüm BU DEPODA çalışan ajanlar içindir; Fusion'ın ürün davranışı değildir.
Fusion kullanıcının kendi projesinde `.env` okur (`config/loader.py`) ve
kullanıcı istediğinde içeriğini modele iletir — maskeleme yapmaz.

- Bu deponun `.env` dosyası okunmaz, içeriği hiçbir yere yazılmaz, commit'lenmez.
  Sebep: burada kullanıcının gerçek API anahtarları duruyor.
- API anahtarı, token veya kişisel veri koda, log'a, teste ya da dokümana girmez.

## Commit

- Commit mesajları conventional commit formatında yazılır: `feat(scope): …`, `fix(scope): …`, `refactor(scope): …`, `test(scope): …`, `docs: …`, `chore: …`.
- Açıklama kısmı Türkçe yazılır.
- **Commit mesajında faz/aşama/sprint numarası geçmez.** Mesaj yapılan işi anlatır; "Faz 1", "Adım 2" gibi etiketler yazılmaz. Faz kavramı yalnızca planlama içindir, git geçmişinde yeri yoktur.
- Commit mesajına author/co-author bilgisi eklenmez.
- Kalite kapısından geçmemiş kod commit edilmez.

## Branch

- Branch açılması ayrıca belirtilmedikçe yeni branch açılmaz; `main` üzerinden çalışılır.
- Force push, hard reset ve history rewrite yapılmaz.
