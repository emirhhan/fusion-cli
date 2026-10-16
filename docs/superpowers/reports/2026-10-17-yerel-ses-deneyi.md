# Fusion ücretsiz yerel ses — ölçüm ve uygulama

17 Ekim 2026. Kullanıcı ücretli ses istemiyor. API ses bağlantısı açılmadı.

## Araştırma ve gerçek yerel deneme

Mac: arm64 Apple Silicon,16GiB RAM. MLX/MLX Audio kurulu değildi. Kullanıcının yerel model tercihi kapsamında bağımsız `/Users/motogate/Desktop/Fusion-Kabul-2026-10-16/voice-lab-env` oluşturuldu. Ana Fusion `.venv` ve proje bağımlılıkları değiştirilmedi.

Standart Qwen3-TTS resmi dil listesinde Türkçe yok. Chatterbox MLX mevcut `generate` yöntemi stream parametresini desteklemediğini belirtiyor. KugelAudio'nun belgelenmiş bfloat16 bellek gereksinimi (~17GB) bu cihazın toplam belleğini aşıyor. Bunlar düşük gecikmeli Türkçe varsayılanı yapılmadı.

OmniVoice `mlx-community/OmniVoice-bf16`, sabit revizyon `8fb0b754cad788aaefec690cd55c207e8a628f85` (~1,5GiB ağırlık) indirildi. Ayrı test script'i HF_HUB_OFFLINE=1 / TRANSFORMERS_OFFLINE=1 ile çalıştı; API servisi yok. Metin: “Merhaba, buradayım. Seni dinliyorum.” 24kHz,2,6sn çıktı:

| Deneme | Sentez süresi | Not |
|---|---:|---|
| Model yükleme |12,299sn|İlk yükleme, sentezden ayrı|
|8adım|3,485sn|İlk derleme/ısınma etkisi dahil|
|16adım|2,276sn|Sıcak model|
|32adım|4,469sn|Sıcak model|

Ses dosyaları `local-omnivoice-tr-{8,16,32}.wav`; ölçüm `local-omnivoice-benchmark.json` ve script `voice-lab-benchmark.py`. Modelin dalga ürettiği doğrulandı; Türkçe kelime doğruluğu/doğallığı insan dinleme kabulü yapılmadı. Kısa sesin tamamlanmasını beklediği ve Piper'dan yavaş olduğu için uygulama varsayılanına alınmadı. Daha az adımın kaliteyi koruduğu varsayılmadı. Üç deneme farklı adım ve ısınma koşullarındadır, kontrollü kalite kıyası değildir.

## Uygulanan yerel düzeltmeler

- Sık tekrar eden kısa yanıtın WAV verisi bellekte sınırlı tutulur (160karakter/16kayıt). Dosya yolu veya oynatıcı paylaşılmaz; her oynatma kendi dosyasını alır. Model/config mtime veya hız/tını ayarı değişirse eski ses kullanılmaz. Uzun cevaplar önbelleğe alınmaz.
- Talk ses tercihlerini okuduğunda ortak niyet kataloğunun dört yanıtı sessizce hazırlanır. Arayüz tercihleri önce gösterilir; hazırlık main event loop'u veya ayar ekranını bekletmez. Eksik model durumunda indirme/ağ çağrısı yapılmaz.
- `ses.konus` da tracked worker kullanır. Arka plandaki model ön hazırlığının kilidinde bekleyen doğrudan ses çağrısı artık dinleme/durdurma RPC'lerini bloklamaz. Bu durum RED/GREEN testle doğrulandı.
-160karakter sınırında bitişik tam cümleler tek ses parçası olur. Kısa cevapta cümle başına ayrı afplay geçişi kalkar; uzun cevaplarda mevcut ön yükleme/iptal sahipliği korunur. Bu değişiklik ses modelinin doğallığını kendiliğinden artırdığı iddiası değildir.

Yerel Piper kaynak ölçümü: dört yanıtı hazırlama toplam1,444sn; ardından aynı yanıtın WAV verisini üretme/yazma0,159–0,567ms. Yalnız sentez/önbellek ölçümüdür; mikrofon, LLM yanıtı, ses aygıtı başlangıcı ve kullanıcının işittiği toplam gecikmeyi içermez. Kanıt `local-piper-cache-benchmark.json`.

## Doğrulama

19 TS dosyasında175 ses/uygulama testi geçti.55 hedefli Python testi, Ruff ve dört kaynakta mypy geçti. TypeScript kontrolü geçti. Kod incelemesindeki synchronous direct-speech kilidi ve ES2020 `.at()` hatası giderildi. Yeni native paket kaydı tamamlanınca bu belgeye eklenir.

ChatGPT/Siri düzeyinde ses kalitesi kabulü hâlâ yok. Ses tanıma/üretme yerel kalır; Fusion'ın mevcut seçili görev modellerinin çalıştığı yer bu ses değişikliğiyle değiştirilmez. Tamamen çevrimdışı genel amaçlı LLM ajanı teslim edildiği iddia edilmez.

## Birincil kaynaklar

- https://github.com/QwenLM/Qwen3-TTS/blob/main/README.md
- https://github.com/Blaizzy/mlx-audio
- https://github.com/Blaizzy/mlx-audio/blob/main/mlx_audio/tts/models/chatterbox/chatterbox.py
- https://github.com/k2-fsa/OmniVoice
- https://huggingface.co/mlx-community/OmniVoice-bf16

## Paketli çekirdek kontrolü

runtime-06 duman testi geçti. Boş geçici HOME'da yalnız ses modeli dizini bağlanarak `ses.isit` ve iki `ses.hazirla`/`ses.haziri_sil` zinciri doğrulandı. Çekirdek başlangıcı dahil ön hazırlık7,0029sn; ön hazırlanmış aynı cevabın WAV hazırlama RPC'si4,7ms ve1,6ms. Hoparlör veya mikrofon kullanılmadı. Ham kanıt `local-runtime06-benchmark.json`. Başlangıç maliyeti ile sıcak-cache gecikmesi birbirine karıştırılmamalıdır.

Native11/runtime06 derleme, kararlı imza ve app/helper audio-input yetkileri doğrulandı. Önceki sahipli native10 ana süreci kapatılıp native11 aynı native-profile-02 ile açıldı. Gerçek cihaz kabulü bekleniyor; push/yayın yapılmadı.
