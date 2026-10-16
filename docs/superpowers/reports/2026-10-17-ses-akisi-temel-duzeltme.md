# Fusion Talk — ses akışının temel düzeltmesi

17 Ekim 2026. Yerel aday: native-candidate-10; runtime-05. Yayın kabulü değildir.

## Davranış

- Selamlaşma, hal hatır, teşekkür ve duyulma kontrolü tek ortak niyet kataloğundan yanıtlanır. Tam ifade eşleşir; “merhaba füzyon projeyi aç” gibi görevler model yolunda kalır. Evet/hayır ve işlem onayları hazır yanıt sayılmaz.
- Yerel yanıt aynı konuşmanın geçmişine ve gönderim makbuzuna yazılır. Tekrar gönderim ikinci geçmiş oluşturmaz.
- Fusion/Füzyon/Fuzyon hitabı tanınır. Etkileşimden sonra 30 saniyelik konuşma aralığında adı tekrar etmeden devam edilebilir.
- Native tanıma sonucu kendi konuşma segmentinin süresini taşır. Önceki sonucun yeni konuşmanın kısa süresiyle reddedilmesi giderildi. Aynı metnin güvenilir kısmi sonucu, düşük güvenli nihai sonuçla kaybolmaz. Onaylar için bu gevşetme kullanılmaz.
- Boş/sessiz tanıma sonucu ile ses duyulup sözcük çözülememesi ayrılır. Salt VAD veya “hmm” yanıtı kesmez; güvenilir anlamlı söz keser.
- Modelin tamamlanmış yanıtı cümlelere ayrılır. İlk cümle çalarken yalnız sonraki cümle hazırlanır. Hazırlama, oynatmayı başlatma ve dosya temizliği ana olay döngüsünü bekletmez. Geç gelen hazırlanmış ses iptalde oynatılmaz; kapanış worker tamamlanmasını bekler.
- Sesli isteklerin yanıtları requestId ile FIFO izlenir. Art arda konuşma önceki yanıtı ezmez. Metinsiz hızlı terminal sonuç sonraki cevabı kilitlemez.
- Büyüt/küçült menü öğesi kaldırılmıştır. Karakterin etrafında kalıcı araç çubuğu yoktur; sağ tık menüsü ses ayarları, simge durumuna küçültme ve kapatmayı içerir.

## Kanıt

- Ses + uygulama + oturum: 21 test dosyası / 206 test geçti. Son terminal-kimliği regresyonu: 7 store testi geçti. Son oynatıcı iptal testleri: 3/3 geçti; start-ACK yarışında tek stop doğrulandı.
- Python ses hedefli: 52 test geçti. AppSession + yerel niyet + hazır ses deposu: 83 test geçti.
- TypeScript derlemesi, hedefli Ruff ve mypy geçti. Hook lint: sıfır hata, önceden mevcut AccountScreen uyarısı var.
- Native sentetik segment-kaniti, kanal-sadakati, iki-konusma senaryoları çıkış 0. Gerçek mikrofon ölçümü değildir.
- runtime-05 duman testi geçti: sağlık, proje, süreç, oturum, katalog, kontrol, önizleme, ders.
- Paketlenmiş çekirdekte sağlayıcısız üç yerel yanıt geçti. İlk istek başlangıç dahil 0,997 sn; sonraki yerel yanıtlar 0,003/0,004 sn.
- Paketli Piper hazırla/çal/bekle protokolü geçti. İlk sentez/model yükleme 2,030 sn; sonraki 0,120 sn. **afplay taklit edildi; bu süreler duyulan sesin veya mikrofon–yanıt toplamının ölçümü değildir.** Ham kanıt: Fusion-Kabul-2026-10-16/voice-foundation-runtime05.json.

## Sınırlar

Mikrofon/hoparlörlü gerçek kullanıcı kabulü hâlâ gerekir. Bu çalışma ChatGPT Realtime ses modeli değildir; tamamlanmış metin yanıtını cümleler halinde Piper ile seslendirir. Modelin karmaşık görev yanıt süresi, Türkçe ses tınısı ve tüm akustik ortamlarda yankı başarımı bu testlerle garanti edilmez. İlk Piper model yükleme maliyeti devam eder. Native sentezin zaman aşımı/işlem izolasyonu ayrıca iyileştirme alanıdır. Genel ürün kabulündeki oyun/animasyon ve diğer açık kapılar kapanmış sayılmamıştır; push/yayın yapılmamıştır.

## Araştırma

Turn detection, endpointing ve interruption yaşam döngüsü ilkeleri incelendi; yeni ücretli servis veya büyük framework eklenmedi, kaynak kod kopyalanmadı:

- https://docs.livekit.io/agents/logic/turns/
- https://docs.livekit.io/agents/logic/turns/tuning/
- https://github.com/pipecat-ai/pipecat/blob/main/examples/turn-management/turn-management-interruption-config.py
- https://developer.apple.com/documentation/speech/sfspeechrecognitionresult
