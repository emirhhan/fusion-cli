# Fusion Masaüstü Uygulaması — Kurulum

Fusion kendi çalışma zamanını içinde taşır: Python, Terminal, Homebrew ya da ayrı
bir CLI kurulumu GEREKMEZ. İndir, aç, kullan.

Uygulama imzasız dağıtılmaktadır (Apple Developer hesabı ve Windows kod imzalama
sertifikası yok). Bu yüzden her iki işletim sistemi de İLK açılışta bir güvenlik
uyarısı gösterir. Uyarıyı geçme adımları aşağıda; yalnız ilk açılışta gerekir.

## Hangi dosyayı indirmeliyim?

| Bilgisayarın | Dosya |
|---|---|
| Mac (Apple M1/M2/M3/M4 ve sonrası) | `Fusion-macOS-Apple-Silicon.dmg` |
| Mac (Intel) | `Fusion-macOS-Intel.dmg` |
| Windows 10/11 (64-bit) | `Fusion-Windows-Kurulum.exe` |

Mac'inin hangisi olduğunu bilmiyorsan:  menüsü → **Bu Mac Hakkında**.
"Çip: Apple ..." yazıyorsa Apple Silicon, "İşlemci: Intel" yazıyorsa Intel.

## macOS — ilk açılış

1. İndirdiğiniz DMG'yi açın.
2. `Fusion.app` simgesini **Applications / Uygulamalar** klasörüne sürükleyin.
3. İlk kez Finder'da `Fusion.app` üzerine sağ tıklayın ve **Aç** seçeneğini seçin.
4. macOS uyarısında yeniden **Aç** düğmesine basın.

Bu işlem yalnız ilk açılışta gerekir. Sonraki kullanımlarda Fusion'ı normal
biçimde Uygulamalar klasöründen açabilirsiniz. İlk açılışta Fusion çalışma
zamanını doğrular ve hazırlar; ilerleme uygulama penceresinde görünür.

## Windows — ilk açılış

1. İndirdiğiniz `Fusion-Windows-Kurulum.exe` dosyasına çift tıklayın.
2. "Windows bilgisayarınızı korudu" (SmartScreen) uyarısı çıkarsa
   **Ek bilgi** bağlantısına, ardından **Yine de çalıştır** düğmesine basın.
3. Kurulum sihirbazını tamamlayın. Fusion yalnız sizin kullanıcı hesabınıza
   kurulur; yönetici parolası istemez.
4. Başlat menüsünden Fusion'ı açın.

Çalışma zamanı `%LOCALAPPDATA%\Fusion\runtime` altına kurulur. Gezici (roaming)
profil kullanılmaz: paket yüz megabaytlarca makineye özel ikili taşır ve gezici
profile girerse her oturum açılışında ağ üzerinden kopyalanırdı.

## Kurulum yarıda kalırsa

Önce Fusion'ı kapatıp yeniden açın. Sorun sürerse **Ayarlar → Çalışma Zamanı →
Çalışma zamanını onar** yolunu kullanın. Onarım yalnız Fusion'ın paketli çalışma
zamanını yeniler; projelerinize ve kullanıcı ayarlarınıza dokunmaz.

## Kaldırma

- **macOS:** Uygulamalar klasöründeki uygulamayı Çöp Sepeti'ne taşıyın.
- **Windows:** Ayarlar → Uygulamalar → Yüklü uygulamalar → Fusion → Kaldır.

Her iki durumda da projeleriniz ve Fusion kullanıcı verileri ayrıca silinmez.
