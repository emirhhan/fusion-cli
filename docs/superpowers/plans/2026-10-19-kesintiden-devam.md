# Kesintiden aynı işin devamı

Kullanıcı Fusion'ın durdurulan kodlama turuna önceki araç kanıtlarıyla devam
etmesini ve VFS-BOT denemesini 18 Ekim 23:16'daki ilk durdurma noktasına
döndürmeyi istedi. Yeni görev kendiliğinden başlatılmayacak; kullanıcı devam
komutunu gönderecek.

1. İptalin açık sohbet geçmişindeki araç adımlarını kaybettiğini testle göster.
2. Günlüğü iptal anında belleğe geri al; yeniden açılışta aynı bağlamı kullan.
   Araç grubu ortasında kesilme ve iç düzeltme turları da kaydedilir.
   Sonucu kaydedilmemiş eylem belirsizdir, otomatik yeniden yürütülmez.
3. İptal temizliği kalıcılaşmadan sonraki turun başlamasını önle. Devam notu
   asıl işi ve boşlukları korunmuş gerçek proje kökünü taşır; UI'ya sızmaz.
4. İlgili regresyonlar, Ruff, mypy ve paketli çalışma zamanı smoke kontrolü.
   Bağımsız kod incelemesi. Kurulu yerel uygulamaya doğrulanmış runtime ver.
5. Mevcut proje, konuşma ve günlüklerin yedeğini al. İlk koşunun tamamlanan araç
   olaylarından devam günlüğünü yeniden kur. İkinci koşuyu etkin konuşmadan
   arşive taşı. Önceki kaynak dosyalarıyla eşleşen dosyalara dokunma.

Başarı ölçütü: devam çağrısına verilen geçmiş oluşturulan dosyaları, son gerçek
hatayı ve araç sonuçlarını içerir; kesilmiş araç otomatik tekrarlanmaz; aynı
açık sekme ve yeniden başlatma yolları test edilir. Gerçek modelin her zaman
aynı stratejiyi seçeceği garanti edilmez.
