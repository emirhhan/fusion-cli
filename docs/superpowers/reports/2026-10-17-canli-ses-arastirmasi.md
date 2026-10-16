# Fusion — gerçek zamanlı doğal konuşma araştırması

17 Ekim 2026. Kullanıcı native10 konuşma kalitesini yetersiz buldu. Önceki ses akışı düzeltmeleri ChatGPT düzeyinde ses kalitesi kabulü değildir.

## Bulgular ve ayrım

Fusion native10: Apple Speech → tamamlanmış metin → görev motoru → tamamlanmış cevap → Piper cümle sentezi. Ön yükleme ve hazır yanıtlar bekleme sürelerini azaltır; ses üretim modelini konuşmanın duygusu, vurgu ve söze girme işaretleriyle çalışan doğrudan ses modeline dönüştürmez. Önceki sentez benchmark'ları gerçek cihaz akıcılığı kanıtı değildir; kullanıcının reddi kabul durumunda esas alınır.

OpenAI'nin güncel resmi belgeleri üç ayrı mimari tanımlar: zincirli STT/metin/TTS, Realtime ve GPT-Live. GPT-Live full duplex çalışır: aynı anda konuşup dinleyebilir; istemci delegasyonu ile mevcut bir görev motorunu kullanabilir. Realtime ile aynı oturum protokolü değildir. GPT-Live için `session.delegation.created` görev metni taşımaz; uygulama zaman damgalı transcript ve mevcut görev durumundan bağlam kurar. Transcript parçacığı doğrudan çalıştırılacak tam bir talimat veya onay sayılamaz.

Kullanıcının “geçtiğimiz aylardaki güncelleme” ifadesinin hangi ChatGPT sürümüne karşılık geldiği ve ChatGPT'nin içindeki tam model/pipeline bu kaynaklarla kesinleştirilmemiştir. GPT-Live'ın ChatGPT'nin o güncellemesindeki özel uygulamanın birebir aynısı olduğu iddia edilmez. Açık belgelerde Fusion'a uygulanabilir en doğrudan mimari olarak değerlendirilmiştir.

## Önerilen uygulama

1. Ücretsiz yerel yol korunur; ücretli canlı sağlayıcı sessiz varsayılan veya fallback olmaz.
2. Mikrofon ve hoparlör doğrudan WebRTC medya track'leri üzerinden ses modeliyle konuşur. Anahtar yalnız çekirdekte kalır. Piper canlı konuşmayı tekrar seslendirmez; native STT ile çift mikrofon sahipliği oluşmaz.
3. Sohbet ve zor işler ayrılır. Doğal konuşma ses modelindedir; dosya/kod/MCP/agent ve işlem onayları mevcut Fusion motorundadır. Görev sürerken konuşma devam eder.
4. İstemci delegasyonu requestId/sessionId ile bağlanır. Transcript fragment'ları özgün boşlukları, sıralaması ve zamanlarıyla saklanır. Kısa “evet”, tüm konuşma ve açık soru bağlamı olmadan işlem onayı değildir.
5. Görev sonucu doğrulanmadan işlem tamamlandı denmez. `session.commentary.append` kısa doğrulanmış sonucu geri taşır; özel düşünceler taşınmaz. Sağlayıcı başına tek mesajda 500 token sınırı gözetilir.
6. Kapanış `session.close` → `session.closed` doğrulaması → track/peer/kanal temizliği sırasındadır. Başlatma sırasında iptal ve geç gelen oturumlar da kapatılır. Günlükte sır/ham SDP/transcript tutulmaz.
7. İlk ses gecikmesi, kullanıcı cümlesi bölünmesi, düzeltme, söz kesme, arka plandaki görev ve gerçek Türkçe ses doğallığı ayrı gerçek cihaz senaryolarıyla sınanır. Unit/fake test doğallık kabulü değildir.

## Bu turda yapılan ve yapılmayan

`providers/live_voice.py` + paketli `providers/data/live-voice.json`: sabit resmi uçta WebRTC teklifini sunucu anahtarıyla değiştiren **etkin olmayan** adaptör. Açık ücret kabulü veya anahtar yoksa ağa çıkmaz; 401/403,429,HTTP/ağ hatası ve bozuk yanıtlar sırsız Türkçe hata verir. Varsayılanlar resmi belgeye göre gpt-live-1, marin, client delegation. 11 sahte ağ testi ve Ruff/mypy geçti.

Bu adaptör henüz Talk UI, mikrofon, geçmiş veya görev motoruna bağlanmadı. Çalışan native10 değiştirilmedi. Gerçek API oturumu açılmadı, ücret oluşacak çağrı yapılmadı, yeni paket veya push yapılmadı. Sağlayıcı/maliyet tercihi soruldu; yanıt bekleniyor. Kullanıcıya GPT-Live / mevcut Gemini canlı ses / ücretsiz yerel seçenekleri sunuldu. Tercih geldiğinde bu plan seçilen sağlayıcının kendi protokolüyle somutlaştırılacak.

## Maliyet ve gerekli karar

Resmi model sayfası: GPT-Live ses oturumu 0,05 USD/dakika, saniye bazında; 60 dakika yaklaşık3 USD. Görev motoru/model/araç maliyeti ayrıca. ChatGPT aboneliği yerine API hesabı/anahtarı gerekir. WebRTC başlatma aşamasında 15 saniyelik başlangıç ücretlendirmesi vardır; çalışmaya geçince süre hesabına sayılır. Sürekli wake için ücretli bağlantıyı gün boyu açık tutmak varsayılan yapılmamalıdır. Mevcut Gemini anahtarının canlı modele erişimi/kotası henüz sınanmadı. Yerel yol için aynı ses kalitesi garantisi verilmez.

## Birincil kaynaklar

- https://developers.openai.com/api/docs/guides/voice-agents
- https://developers.openai.com/api/docs/guides/live
- https://developers.openai.com/api/docs/guides/live-delegation
- https://developers.openai.com/api/docs/guides/voice-webrtc?api=live
- https://developers.openai.com/api/docs/guides/live-conversations
- https://developers.openai.com/api/docs/models/gpt-live-1
- Resmi örnek uygulama (bağlantısı resmi başlangıç belgesinde): https://github.com/openai/openai-live-console
