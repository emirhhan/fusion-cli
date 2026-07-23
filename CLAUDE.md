# CLAUDE.md

- Bu dosya her mesajda okunur ve yönlendiricidir.
- Kod ve karar vermeden önce [RULES.md](RULES.md) okunur — mimari, isimlendirme ve proje kuralları oradadır.
- Bu dosyalarda yazmayan bir şey kendi başına varsayılmaz, kullanıcıya sorulur.

## Projenin Amacı

- Bu proje, `/Users/ok/Desktop/fusion-cli-ilk-hali` (eski proje) kodunun katmanlı, generic ve test edilebilir bir yapıya sıfırdan taşınmasıdır.
- Eski proje referans kaynaktır: **davranış birebir korunur**, yapı temizlenerek taşınır.
- Eski projenin tam özellik envanteri `fusion-cli-ilk-hali/FUSION-CLI-OZELLIK-RAPORU.html` dosyasındadır; bir özelliğin ne yaptığı sorusu önce oradan ve eski koddan cevaplanır.
- Eski projedeki tek-kullanımlık çözümler, kopyala-yapıştır tekrarlar ve tek dosyaya yığılmış sorumluluklar taşınmaz; ilgili kod merkezi yapıya bağlanarak taşınır (RULES.md "Genel Tasarım" ve "Katman Sınırları").
- Ürünün kimliği değişmez: ücretsiz LLM'lerle çalışan, iki motorlu (agent + fusion), öz-öğrenen, terminalde yaşayan bir kodlama asistanı.

## Geliştirme Akışı

- Taşıma **modül modül** ilerler; sırada olmayan modüle dokunulmaz.
- Büyük geliştirmeler her zaman **faz faz** planlanır; faz planı onaylanmadan kod yazılmaz.
- Her faz sonunda kalite kapısı çalıştırılır: `ruff check` + `mypy` + `pytest`. Üçü de temizse commit atılır, ancak ondan sonra bir sonraki faza geçilir.
- Bir faz yarım bırakılmaz; kapsam büyürse faz bölünür, kapsam sessizce genişletilmez.
- Davranış değişikliği gerektiren iyileştirmeler taşıma sırasında yapılmaz; "sonra" listesine (`docs/BACKLOG.md`) not edilir.
- Eski projede tespit edilmiş hatalar taşınmaz; düzeltilerek taşınır ve commit mesajında belirtilir.

## Taşıma Disiplini

- Her modül taşınırken önce **eski davranış okunur ve yazıya dökülür**, sonra yeni yapıya yazılır; hafızadan yeniden yazılmaz.
- Bir özellik taşınırken testi de aynı fazda yazılır; testsiz modül "taşındı" sayılmaz.
- Eski projedeki sabitler (timeout, eşik, limit, model kimliği) uydurulmaz; eski değer birebir taşınır, değişecekse ayrıca konuşulur.
- Kullanıcıya görünen tüm metinler (prompt, hata, yardım) eski projedeki Türkçe karşılığıyla taşınır.

## Dil

- Kod içi her şey Türkçe kalır: docstring, yorum, log, hata mesajı ve kullanıcıya görünen tüm CLI metinleri Türkçe yazılır.
- Tanımlayıcılar (modül, sınıf, fonksiyon, değişken adları) Python ekosistem uyumu için İngilizce ve PEP 8'e uygun yazılır — eski projedeki düzenin aynısı.
- Detay: RULES.md "Dil".

## Sırlar

- `.env` dosyası okunmaz, içeriği hiçbir yere yazılmaz, commit'lenmez.
- API anahtarı, token veya kişisel veri koda, log'a, teste ya da dokümana girmez.

## Commit

- Commit mesajları conventional commit formatında yazılır: `feat(scope): …`, `fix(scope): …`, `refactor(scope): …`, `test(scope): …`, `docs: …`, `chore: …`.
- Açıklama kısmı Türkçe yazılır (eski repodaki düzenin aynısı).
- **Commit mesajında faz/aşama/sprint numarası geçmez.** Mesaj yapılan işi anlatır; "Faz 1", "Adım 2" gibi etiketler yazılmaz. Faz kavramı yalnızca planlama içindir, git geçmişinde yeri yoktur.
- Commit mesajına author/co-author bilgisi eklenmez.
- Kalite kapısından geçmemiş kod commit edilmez.

## Branch

- Branch açılması ayrıca belirtilmedikçe yeni branch açılmaz; `main` üzerinden çalışılır.
- Force push, hard reset ve history rewrite yapılmaz.
