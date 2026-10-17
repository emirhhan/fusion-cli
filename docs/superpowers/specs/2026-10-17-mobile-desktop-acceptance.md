# Mobil ve masaüstü iyileştirme kabulü

## Kullanıcı davranışı

- Normal onaylar sohbet içinde tek dokunuşla iletilir; Onaylar aynı isteklerin toplu görünümüdür. Yüksek etkili veya oturum boyunca izin kararında telefon da işlem ayrıntılarıyla açık ikinci teyit gösterir.
- Her karar gerçek host makbuzu taşır. Yürütücü cevabı kabul etmediyse başarı gösterilmez; aynı kararın güvenli yeniden denenmesi görev eylemini çoğaltmaz.
- Hesapla giriş yapan gözlem yetkili cihaz ekran iznini telefonda açıkça onaylayabilir ve bu cihaz için hatırlatabilir. Durdur ve cihaz iptali hatırlanan izni kaldırır. Durum sorgusu ve kare alma kendi başına yeni izin oluşturmaz.
- Eski bekleyen ekran isteği telefondaki teyitle tamamlanabilir. Akış kendiliğinden tekrar tekrar onay talebi üretmez.
- Ayarlardaki ek kapsam tercihleri yerel, sürümlü ve izin listesi doğrulamalı depoda tutulur. Bu tercihler mevcut cihazın yetkilerini değiştirmez; yalnız sonraki eşleştirme koduna uygulanır.
- Mini dock gerçek pencere kimliği+süreç kimliği ve Chrome sekme kimliği kullanır. Kapanmış hedefe sessizce başka pencere seçilmez. Manuel sekme odağı, ajanın arka plan sekme bağını değiştirmez.
- Kullanıcının mevcut ekranının telefon tarafından izlenmesi masaüstünde bir kopya popup açmaz. Küçük önizleme yalnız gerçek, hedefi bilinen arka plan ajan aracına bağlanır. İşlem veya hedef yakalama sırasında değişirse eski kare gösterilmez.
- Arka plan masaüstü araçları genel fare/klavye girdisi göndermez: pencereye özel ScreenCaptureKit görüntüsü ve desteklenen AX öğelerinde press/set_value kullanılır. Sistem Ekran Kaydı ve Erişilebilirlik izinleri gerekir. İlgili uygulamanın desteklemediği eylem veya eksik kimlik açık hata döndürür.
- Nasıl yapılır bölümü açık satırlar, tema renkleriyle rozetler ve kırpılmayan görseller kullanır.

## Sınırlar

macOS'taki gerçek arka plan uygulama etkileşimi, her uygulama için izole bir sanal masaüstü vaat etmez. Uygulama kendi eylemine tepki olarak yeni pencere açabilir veya odak isteyebilir. Chrome DOM işlemleri arka plan sekmesinde yapılabilir; görünür sekmeyi değiştirmeden Chrome sekme ekran görüntüsü bu sürümde desteklenmiyorsa farklı ekran görüntüsü gösterilmez. İşletim sisteminin TCC izinleri Fusion içindeki onaylarla atlanmaz.

## Yayın

Kullanıcı kodun push edilmesini istedi. `.github/workflows/desktop.yml` ana dal push'unda doğrulama/paket üretimi yapıyor; release işi yalnız `refs/tags/v` için çalışıyor. Release-evidence de sürüm etiketi veya elle tetiklemeyle çalışıyor. Bu görevde sürüm etiketi ve yayın oluşturulmayacak. Kullanıcı son onayı vermeden release yayımlanmayacak.
