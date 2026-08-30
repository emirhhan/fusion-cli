# Değişiklik günlüğü

Biçim [Keep a Changelog](https://keepachangelog.com/tr/1.1.0/) esaslıdır.
Sürümleme [SemVer](https://semver.org/lang/tr/) uyarınca yapılır.

## [0.3.0a4] — 2026-08-30

- Ses ayarları ilk açıldığında geciken bir eşitlemenin kullanıcının hızlı sürgü
  hareketini eski değerle ezebilmesi düzeltildi.
- Sürgü kaydetme yarışı tekrarlı regresyon koşusuyla doğrulandı.

## [0.3.0a3] — 2026-08-30

- macOS ve Windows masaüstü paketleme ortamlarına Piper ses motoru bağımlılığı
  eklendi; temiz CI makinesinde çalışma zamanı üretimi artık eksik paket bilgisiyle
  durmuyor.
- Ses sürgüsü testi gerçek tarayıcı `input` olayına geçirildi; macOS Intel ve
  Windows ortamlarındaki sahte olay zamanlaması farkı giderildi.
- Masaüstü CI bağımlılık sözleşmesi regresyon testine alındı.

## [0.3.0a2] — 2026-08-30

- Masaüstü Ayarlar ekranına oturumluk token, tahmini maliyet ve ölçülmüş model
  sağlığı özeti eklendi.
- Ses hızı, tını, özel Piper modeli ve çevrimdışı Türkçe model indirme Ayarlar'a
  taşındı.
- Windows WebView'da sürgü bırakılırken eski değerin kaydedilebildiği olay
  sıralaması düzeltildi.
- Ayarlar'ın kaydırma altındaki kullanım ve ses kartları geniş/dar görsel
  regresyon testlerine alındı.

## [0.3.0a1] — 2026-07-26

İlk kamuya açık alfa. Bu sürümün ağırlığı yeni özelliklerde değil, **sessizce
çalışmayan şeylerin bulunmasında**: aşağıdaki hataların çoğu kod "başarılı"
görünürken arka planda hiçbir iş yapmıyordu.

### Eklenenler

- **`/verify`** — projeyi tanıyıp doğrulama planı çıkarır (pytest, ruff, mypy,
  npm/pnpm/yarn scriptleri, cargo, go, make), planı gösterir ve onaylanırsa
  `config.yaml`'a yazar. Otomatik açılmaz: keşif tahmindir, yanlış tahmin kapıyı
  her turda düşürür.
- **`/undo`** — son agent turunun dosya değişikliklerini geri alır. Yalnızca
  agent'ın dokunduğu dosyalar; kullanıcının elle yazdıklarına dokunulmaz.
- **`--add-dir`** — proje kökünün yanında erişime açılacak dizin.
- **`/provider`** — hangi sağlayıcının kullanılacağını seç (`auto` | `nvidia` |
  `openrouter`). Tek sağlayıcıya kilitlenince ötekine hiç istek gitmez: bir
  sağlayıcının tükenmesi ötekini de tüketiyordu.
- **Kurulum sihirbazı anahtar sorar.** OpenRouter zorunlu, NVIDIA NIM opsiyonel.
  83 küratörlü ders otomatik yüklenir: indiren herkes eğitilmiş başlar.
- **Model zincirleri kurulu anahtarlara göre budanır.** İki sağlayıcıdan biri
  yeterlidir; olmayanın modelleri zincirden düşer.
- **Doğrulanmış sentez** (`verified_synthesis`) — hakem önce çalışır, kararı
  senteze taşınır. Paralel kipte sentez kazananı bilmiyordu.
- **Eval: tekrarlı koşu** (`--repeat N`) ve geçme oranı. Kararsız görevler adıyla
  raporlanır.
- **Eval: tur transkripti.** Her koşu `_transkript.jsonl` bırakır (araç çağrıları,
  sonuçları, model hataları). "Agent neden hiçbir şey yapmadı" sorusu artık
  sonradan cevaplanabiliyor.
- **Eval: kota tükenmesi görev başarısızlığından ayrılır.** Sağlayıcı 429 verdiğinde
  koşu durur ve rapor YAZILMAZ; yarım ölçümü geçerli sanmak yanlış sonuçlara yol
  açıyordu.
- **Eval: `setup`** ile göreve başlangıç dosyası verilebilir; bug fix ölçmenin
  ön koşuluydu. On yeni görev — üçü agent’ın YAPMAMASI gerekeni ölçüyor
  (kök dışına yazma, prompt injection, kullanıcı içeriğini silme).
- **Ders belleği projeye kapsanır.** A projesinde öğrenilen B'de hatırlanmaz;
  genel yordamsal dersler her projede kalır. Göç gerekmez.

### Değişenler

- **Kademe merdiveni NVIDIA NIM omurgasına taşındı.** OpenRouter'ın ücretsiz
  kotası günde 50 istek (≈12 fusion turu); NIM'inki çok daha geniş. Modeller
  katalogdan değil **yoklanarak** seçildi — katalogdaki birçok model `NotFound`
  dönüyor ya da zaman aşımına uğruyor.
- **Dosya erişimi varsayılan olarak proje köküyle sınırlı.** Kısıtlama opt-in
  bırakıldığı sürece kimse açmıyordu.
- **Gözetimsiz kabuk çalıştırma kara listeden beyaz listeye geçti.** Tanınmayan
  her komut sorulur. Kara listeye kalıp eklemek bir sonraki kaçış yolunu kapatmaz.
- **Dersler talimat değil ÖNERİ olarak enjekte edilir** ve güvenlik kararlarını,
  kullanıcı talimatını, araç izin akışını geçersiz kılamaz.
- **Kota hatası gerçekten işe yarayan yönlendirme verir.** Eski mesaj "farklı bir
  model dene" diyordu; sınır hesap başına olduğu için bu yanlış tavsiyeydi.

### Düzeltilenler

- **Doğrulama kapısı hiç düzeltme turu açmıyordu.** Komut çıktısı `DEVNULL`'a
  gidiyor, bulgu üretilmiyor, motor da bulgu yoksa döngüyü kırıyordu: `pytest`
  kırmızıyken agent düzeltmeye hiç başlamıyordu.
- **REPL'de doğrulama kapılarının hiçbiri kurulmuyordu.** `tool_context`
  geçirilmediği için web, tarayıcı ve görsel kapılar sessizce kapalıydı.
- **Boş `.env` satırı gerçek anahtarı gölgeliyordu.** Kurulum "tamam" diyor,
  hiçbir model çağrılamıyordu.
- **`/type` agent turunda uygulanmıyordu**; `task_model_map` REPL'de etkisizdi.
- **Seçim ekranı REPL'in event loop'unda çöküyordu.**
- **`defaults.yaml`'da `tiers` iki kez tanımlıydı**; 166 satır ölü koddu ve
  çalışan merdiven bozuktu (`medium` en büyük modeli, `premium` daha küçüğünü
  kullanıyordu).
- **Uzun model listeleri ekranı taşırıyordu** (327 model); artık sayfalanır.
- **Dosya yazımı atomik değildi**; yarıda kesilme çalışan dosyayı bozabiliyordu.
- **Alt-ajan değişiklikleri doğrulama kapısından kaçıyordu.**
- **Hakem ve sentez aday metnini talimat sayabiliyordu** (prompt injection).

### Bilinen sınırlar

- **MCP yok.**
- **`run_shell` kök kısıtlamasına tabi değil.** Onay katmanı savunmadır, kum
  havuzu değil: sınır aşılabilir ama sessizce aşılamaz. Ayrıntı `docs/BACKLOG.md`.
- **Eval seti dar.** 18 görev. Kolay blok tavana vurmuş (12 görev 3/3); ayırt
  etme gücü beş zor görevde. Tek sağlayıcıya kilitlenmiş ölçümde **14/15 ve 13/15**.
- **Gürültü tabanı ~1-2 koşu (15'te), görev bazında ±2.** Aynı yapılandırmanın iki
  koşusu arasındaki fark bu kadar; daha küçük A/B farkları yorumlanamaz.
- **`workflow_mode` ve `playbooks` varsayılan kapalı.** workflow ölçüldü: kaliteyi
  artırmıyor (8/15 → 9/15, gürültü sınırında), model çağrısını yarıya indiriyor
  ama süreyi ikiye katlıyor. `playbooks` hiç ölçülmedi.
