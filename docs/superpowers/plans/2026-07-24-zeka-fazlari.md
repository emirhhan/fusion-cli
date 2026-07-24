# Zekâ Geliştirme Fazları

Amaç: fusion-cli'yi ücretsiz/uzak modellerle (ağırlıklara erişim YOK) daha güvenilir
kılmak. Model eğitimi/fine-tune YOK; yalnızca bağlam, hafıza, retrieval, doğrulama.

## Uygulama kuralları (her faz için geçerli)
- Fazlar sırayla; sıradaki faza yalnızca öncekinin kalite kapısı temizse geçilir.
- Kalite kapısı: `ruff check` + `mypy` + `pytest` — üçü de temiz olmadan commit yok.
- Test aynı fazda yazılır; testsiz modül "bitti" sayılmaz.
- Davranış birebir korunur; yeni yetenekler MEVCUT akışı bozmadan, ek/opt-in eklenir.
- Kod içi metinler Türkçe (docstring/yorum/log/hata/CLI); tanımlayıcılar İngilizce/PEP8.
- Her faz sonunda tek conventional commit; mesajda faz/adım numarası GEÇMEZ.

## Mevcut durum (kod okunarak doğrulanmış — varsayma, dosyaları aç)
- `src/fusion_cli/core/memory.py`: `Lesson`, `LessonKind`, `LessonSource`, `Feedback`
  (delta'lı), `Outcome`, `ModelStats`, `PerformanceMemory`/`LessonMemory`/`CodeIndex`
  protokolleri. `Lesson` alanları şu an: `text, kind, task, source`.
- `memory/store.py` ChromaDB, `memory/lessons.py` ders belleği, `memory/seed.py`
  küratörlü `SEED_LESSONS`, `memory/performance.py` model performansı (`Feedback.delta`
  ile decay), `memory/code_index.py`+`chunking.py`+`embeddings.py` retrieval.
- `engines/agent/learning.py` ders çıkarımı (araç çağrısı olan turda), `reflexion.py`
  hata sonrası bedava not, `review.py` öz-eleştiri (kritik model + tek düzeltici tur).
- `engines/fusion/judge.py` aday hakemliği.
- Ders geri çağırma: `recall(task, limit=4)`, anlamsal benzerlik. Retrieval yalnızca
  embedding cosine (lexical/BM25 YOK). Ders decay YOK. Ders metadata (güven/sayaç) YOK.

---

## Faz 0 — Ölçüm iskeleti
Neden önce: değişikliğin işe yarayıp yaramadığı ancak eski/yeni karşılaştırılarak bilinir.
- `evals/` altında 20-40 görevlik set (JSON/YAML): her görev = istek + başarı ölçütü
  (komut çıkış kodu, beklenen dosya değişimi ya da anahtar-kelime kontrolü). Secret/PII yok.
- `evals/runner.py`: seti çalıştırır, metrik toplar — `task_success`,
  `first_attempt_success`, `retries`, tur başına model-çağrısı sayısı, süre.
- Metrikleri tek JSON'a yazar; iki çalıştırmayı diff'leyen küçük karşılaştırıcı.
- Test: runner saf parçaları (metrik toplama, karşılaştırma) doğrudan test edilir.
Çıktı: sonraki her fazı A/B ölçebilir altyapı. Kod davranışı değişmez.

## Faz 1 — Yerel ders kalitesi (en yüksek kaldıraç)
Neden: bellek çöple dolmasın, işe yaramayan ders sönsün, yerel zehirlenme kapansın.
- `Lesson` dataclass'ına alan ekle: `confidence: float`, `success_count: int`,
  `failure_count: int`, opsiyonel `scope`/`trigger`. Store şemasını göç ettir; eski
  kayıtlar varsayılan güvenle okunur (geriye dönük uyumluluk testi).
- Ders decay: `performance.py`'deki `Feedback.delta` desenini derse uygula. Bir ders
  enjekte edilen tur BAŞARISIZ olursa `failure_count`++ ve güven düşer; başarılıysa tersi.
  `recall` güven ağırlıklı sıralar; güven eşiği altındaki ders enjekte edilmez.
- Yazım kapısı (`learning.py`): yeni ders yalnızca (a) ölçülebilir kanıt varsa
  (araç çıktısı/çıkış kodu), (b) secret/PII içermiyorsa, (c) mevcut çok benzer ders
  yoksa (dedup), (d) mevcut dersle çelişmiyorsa (çelişki işaretlenir) yazılır.
- Test: decay, dedup, kanıt kapısı, çelişki işareti — hepsi saf fonksiyon olarak.
Çıktı: kendini düzelten yerel bellek. Sunucu/dış bağımlılık yok.

## Faz 2 — Hibrit retrieval
Neden: Türkçe metin + İngilizce/kod tanımlayıcılarında salt embedding zayıf.
- Ders ve kod geri çağırmaya lexical (BM25 ya da basit terim skoru) EKLE; embedding ile
  birleştir (ağırlıklı/RRF). Metadata filtresi (task/scope) uygula.
- Reranker MODELİ EKLEME (ayak izini şişirir, ChromaDB zaten ağır). Yalnızca yerel skor.
- Test: lexical skor, birleştirme ve filtre saf fonksiyon; bilinen sorgu→beklenen ders.
Çıktı: doğru dersin gelme oranı artar. Faz 0 ile ölç: `lesson_hit_rate` yükselmeli.

## Faz 3 — Doğrulamayı derse bağla + görev sınıflandırıcı
Neden: ders içindeki "doğrulama" kuralları çalıştırılmazsa dekoratiftir.
- Küçük/ucuz sınıflandırıcı: istek → görev türü (bugfix/refactor/website/test/...).
  Sonuç bağlam kurucuya girer; yalnızca ilgili scope'taki dersler enjekte edilir.
- Ders `verification` alanını projenin MEVCUT kapısına bağla: ilgili turdan sonra
  `ruff`/`mypy`/`pytest` (ya da alt kümesi) çalıştır; sonucu `Outcome`'a yansıt →
  Faz 1 decay'ini besler.
- Test: sınıflandırıcı saf eşleme; doğrulama tetikleme mock'lu.
Çıktı: "test çalıştırmadan tamamlandı deme" gibi kurallar gerçekten uygulanır.

## Faz 4 — Çalıştırılabilir beceri kütüphanesi (opt-in)
Neden: tekrarlayan çok-adımlı işler metin ders yerine deterministik akış olmalı.
- `skills/` veri modeli: `id, preconditions, steps, checks`. Kayıtlı beceriler
  ön-koşul eşleşince önerilir/çalıştırılır; `checks` başarısızsa geri al.
- İlk 2-3 gerçek beceriyle başla (ör. eski kayıtlardan çıkan tekrarlayan tamir akışı).
- Opt-in: varsayılan akış değişmez; beceri yalnızca eşleşince devreye girer.
- Test: ön-koşul eşleşmesi, adım sırası, check başarısızlığında geri alma.
Çıktı: tekrarlayan işler tek deterministik akışla, daha az model çağrısıyla.

## Faz 5 — Deterministik workflow'lar (opt-in, ek)
Neden: zor görevlerde serbest ReAct döngüsü güvenilmez ve maliyeti öngörülemez.
- Görev türüne göre tool-bütçeli akış: localize → plan → minimum patch → syntax/lint/
  test → diff review → yalnızca başarısız aşamayı tekrar. Tur başına SABİT model-çağrısı
  bütçesi (ücretsiz model rate-limit'i için zorunlu kapı).
- MEVCUT `loop.py`'yi değiştirme; yanına ek mod olarak koy, açıkça seçilince çalışsın.
- Test: bütçe kapısı, aşama tekrarının yalnızca başarısız aşamada olması.
Çıktı: zor görevlerde güvenilirlik + öngörülebilir maliyet.

## Faz 6 — Offline prompt optimizasyonu
Neden: promptları elle değil, Faz 0 setiyle ölçerek iyileştir.
- GEPA/DSPy tarzı OFFLINE döngü: planner/critic/localizer promptlarını eval setinde
  çalıştır, skor ölç, varyant üret, kazananı sürümle. Canlı akışta online optimizasyon YOK.
- Eski vs yeni promptu aynı sette karşılaştır; regresyon yoksa yeni sürümü yayımla.
- Test: sürümleme ve seçim mantığı; optimizasyon çağrıları mock'lu.
Çıktı: ölçülü, geri-alınabilir prompt iyileştirmesi.

## Faz 7 — Ortak bilgi paketi (git tabanlı, sunucu YOK)
Neden: doğrulanmış dersleri paylaş; ama otomatik push = zehirlenme riski.
- `knowledge/` altında sürümlü, imzalı paket + manifest. Yalnızca ELLE/CI ile gözden
  geçirilmiş, secret'sız, doğrulanmış dersler girer. `fusion knowledge sync/status`.
- Client ASLA doğrudan global depoya yazmaz; katkı = gözden geçirilen PR.
- Test: manifest doğrulama, imza kontrolü, sync'in yalnızca değişeni indirmesi.
Çıktı: iki kurulum arasında doğrulanmış bilgi paylaşımı; ağır backend olmadan.

---

## Kapsam dışı (bu ürün değil — girme)
- Federated/merkezi öğrenme sunucusu (FastAPI+Postgres+pgvector+Redis+sandbox+GitHub App).
  İki kullanıcı için aşırı; Faz 7 yeterli.
- Model fine-tune / LoRA / distillation / RL. Uzak API modelinin ağırlığına erişim yok;
  bu bambaşka bir ürün (kendi GPU + açık-ağırlık model + serving). İhtiyaç doğarsa
  ayrıca konuşulur.

## Önerilen bitiş hedefi
Sınırlı sürede en yüksek getiri: **Faz 0 → 3**. Faz 4-7 değerli ama opsiyonel/ek.
