# BACKLOG

Taşıma sırasında ortaya çıkan, o fazın kapsamına girmediği için ertelenen işler.
CLAUDE.md gereği kod içine `TODO`/`FIXME` yazılmaz; her şey buraya düşer.

## Taşınacak (eski projede mevcut, henüz taşınmadı)

- Agent motoru: tool-calling döngüsü, reflexion, öz-eleştiri, alt-ajan
- Bellek: performans belleği, ders belleği, semantik kod indeksi, embedding seçimi
- REPL: prompt_toolkit girişi, onay modları, slash komut kayıt defteri, tema
- Gözlemlenebilirlik: Langfuse izleme, oturum maliyeti takibi

## Karar bekleyen

- **Yapılandırma taşması:** `config show` çıktısı büyüdükçe tablo görünümüne geçmeli mi?
- **`--json` çıktısı:** olay veriyolu hazır; JSON dinleyicisi eklemek kolay. Hangi fazda?
- **Sürüm sabitleme:** `requirements.lock` üretilmeli mi, yoksa `pyproject` sınırları yeterli mi?

## Eski projeden düzeltilerek taşınacak hatalar

- Maliyet takibi eski projede yalnızca streaming turlarında çalışıyordu; hakem/sentez/ders
  çağrıları sayıma girmiyordu. Yeni yapıda tek kaynak: `ModelCallFinished` olayı.
- `config.yaml` iki kopya halinde elle senkronlanıyordu. Çözüldü: tek `defaults.yaml`.
- Kod içi varsayılanlar ile dosyadaki değerler ayrışmıştı. Çözüldü: dataclass'ta varsayılan yok.

## İzlenecek

- **Reasoning modeli çıktısı:** `nemotron-3-super` bir reasoning modelidir. Kısa
  `max_tokens` bütçesinde düşünme metni cevabın yerine geçebiliyor (24 token'lık probda
  görüldü; 2048'de sorun yok). Eski projede bunun için `<think>` ayıklaması vardı.
  Agent motoru gelince gerçek bir sorun çıkarsa sağlayıcı dekoratörü olarak eklenmeli.
- **Model kataloğu kayması:** varsayılan modeller sağlayıcı tarafında sessizce kaybolabiliyor
  (`z-ai/glm-5.2` NIM'de hiç yoktu, `tencent/hy3:free` ücretsizlikten çıkmıştı). Modelleri
  canlı katalogdan listeleyen bir komut (`fusion models --fetch`) faydalı olur.

- **`LlmProvider.stream()` henüz kullanılmıyor.** Protokolde tanımlı ve testli; agent
  motoru geldiğinde tüketilecek. Fusion modunda bilinçli olarak akış YOK: hakem ve sentez
  paralel çalıştığı için, akan cevabın ortasına arka plan ilerlemesi düşmesin diye.
- **Hakem eksik puanlama yapabiliyor:** üç aday yanıtladığında hakem bazen ikisine puan
  veriyor. Ayrıştırıcı yalnızca geçerli adları aldığı için sorun çıkmıyor ama puan tablosu
  eksik görünüyor. Prompt'ta "her adaya puan ver" vurgusu denenebilir.

- **Yol sınırlaması yok.** Araçlar proje kökü dışına da yazabilir (eski davranış korundu;
  onay akışı + diff önizlemesi kullanıcıyı koruyor). İstenirse `ToolContext`'e kök dışına
  yazmayı reddeden ya da ayrıca onay isteyen bir kip eklenebilir.
- **`web_search` HTML kazımaya dayanıyor.** İki uç denenerek dayanıklılık sağlandı ama
  sayfa yapısı değişirse ikisi de bozulabilir. Kazıma mantığı saf fonksiyonlarda ve
  testli; uç değişirse yalnızca regex güncellenir.
