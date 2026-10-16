# Sesli konuşmanın kabulü ve yanıt akışı

Kullanıcı yeniden tasarımı ve uygulamayı istedi; ek tasarım onayı isteme talebi yok. Mevcut yerel Apple STT/Piper/Tauri korunur, yeni ücretli servis veya ağır çatı kurulmaz.

1. Tek ortak niyet kataloğu: yalnız tam selamlaşma/hal hatır/teşekkür/hazır mısın ifadeleri model olmadan yanıtlanır. Ek görev, dosya eki, belirsiz onay ve eylem komutları bu yola girmez. Kullanıcı/asistan metni aynı kalıcı geçmişe, gönderim makbuzuyla yazılır.
2. Uyandırma: merhaba/selam + Fusion/Füzyon ve adla biten tanımlı kısa hitaplar desteklenir; uzun görevler kaybolmaz. Yerel yanıtta düşünme görünmez.
3. Tanıma: native callback kendi segmentinin konuşma süresini taşır; yeni VAD segmenti önceki sonucu bozmaz. Aynı segmentte geçerli ve aynı metinli partial, düşük güvenli finalle gereksiz kaybedilmez. Onaylar daha sıkı nihai tanıma yolunda kalır. Sessizlik ve eski callback gerçek hatadan ayrılır.
4. Yanıt oynatma: tamamlanmış metnin cümleleri için hazırlanmış ses/oynatma ayrılır; sonraki cümle çalınanı beklemeden hazırlanır. İptal, hazırlanmış sesi de temizler; sonradan çözülen istek ses başlatamaz. Araç öncesi geçici model metni kesin yanıt gibi okunmaz.
5. Kanıt: yerel niyet/model çağrısı ayrımı, kalıcı geçmiş/makbuz, aynı süreçte çoklu segment, geç final/partial, onay, oynatma/iptal yarışları. Paketli gerçek model ile yerel selamlaşma ve ses üretimi; gerçek mikrofon kabulü ayrı raporlanır.

Kaynaklar (2026-10-16): https://docs.livekit.io/agents/logic/turns/ ; https://docs.livekit.io/agents/logic/turns/tuning/ ; https://github.com/pipecat-ai/pipecat/blob/main/examples/turn-management/turn-management-interruption-config.py . İlkeler uyarlanır; dış kod kopyalanmaz.
