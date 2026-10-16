# Fusion canlı ses geçişi

Kullanıcı ses hızından öte ChatGPT benzeri kesintisiz ve doğal konuşma istiyor. Mevcut Apple STT → görev bitişi → Piper zinciri bu kaliteyi tek başına sağlayamaz. Mevcut geçmiş, görev motoru, onaylar ve ücretsiz yerel yol korunur.

Karar: resmi belgelerdeki doğrudan ses modeli / WebRTC taşıması incelenerek seçilebilir canlı konuşma yolu eklenir. GPT-Live konuşmayı sürdürürken istemci delegasyonu Fusion görev motoruna bağlanabilir. OpenAI API ücretlidir; kullanıcı sağlayıcı/maliyet tercihi gelmeden canlı bağlantı etkinleştirilmez, ücretli ağ çağrısı yapılmaz. ChatGPT'nin özel eğitim ağırlıkları veya iç ürün mimarisi yeniden üretildiği iddia edilmez.

Kabul: tek mikrofon sahibi, kapatmada track/peer/kanal temizliği; eski oturum sonucu yeni sohbete yazılamaz; onaylar yerel modele devredilmez; araç sonucu doğrulanmadan yapıldı denmez; transcript normal konuşmada kalır; bağlantı ve kota hatası anlaşılır; sessiz ücretli fallback yok. Gerçek cihaz ve gerçek sağlayıcı kabulü ayrı, fake bağlantı testleri doğallık kanıtı değildir.

## Kullanıcı kararı — 17 Ekim

Kullanıcı “Tamamen ücretsiz ve yerel kalsın” seçti. Ücretli ses bağlantısı etkinleştirilmeyecek. Yerel ses tarafında resmi Türkçe desteği, Mac uyumu ve ölçülmüş gecikme esastır. Mevcut görev modeli seçimi bu ses tercihiyle kendiliğinden değiştirilmez.

OmniVoice-bf16, ayrı voice-lab ortamında ağsız çıkarımla denendi. 16 adım sıcak sentez2,276sn/2,6sn ses; ilk yükleme12,299sn. Bu haliyle düşük gecikme varsayılanı olamaz. Model ve Python bağımlılıkları ana .venv'e veya uygulama paketine eklenmedi.

Yerel düzeltme: Piper kısa-yanıt WAV önbelleği (≤160 karakter,16 kayıt, model/config mtime ve ses ayarları anahtarda); katalog yanıtlarını Talk açılışında sessiz ön hazırlık; tüm sentez yolları tracked worker; kısa yanıtlar tek ses parçası. Gerçek cihaz doğallık kabulü bu teknik kapılarla verilmez.
