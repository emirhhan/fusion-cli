# Fusion Browser eklentisi: kurulum akışı

## Tek tıkla ne olur

**Ayarlar → Tarayıcı → Eklentiyi kur** (ya da terminalde `fusion chrome-kur`):

1. Eklenti dosyaları kalıcı klasöre kopyalanır
   (macOS: `~/Library/Application Support/Fusion/chrome-extension`, Windows: `%APPDATA%\Fusion\chrome-extension`).
   Uygulama taşınsa ya da güncellense bile yol değişmez.
2. Chrome'un yerel mesajlaşma kaydı yazılır (eklentinin Fusion'ı kendi bulması için).
   macOS'ta `NativeMessagingHosts` bildirimi, Windows'ta `.bat` başlatıcı + `HKCU` kayıt anahtarı.
   `manifest.json` içindeki sabit `key` sayesinde eklenti kimliği klasör yolundan bağımsızdır
   (`dmdljajadkocbomficmpladgajnnidfa`).
3. `chrome://extensions` açılır, klasör yolu panoya konur ve klasör gösterilir.
4. Ayarlar ekranı iki şeyi doğrular ve 4 sn'de bir yeniler:
   - **Chrome'a yüklendi**: Chrome profillerinin `Preferences` dosyası (yalnız okunur) eklentiyi
     yüklü ve etkin gösteriyor mu.
   - **Fusion ile eşleşti**: eklenti köprüye bağlandı mı (`bagli`).

## Senin yapacağın tek şey (Chrome bunu zorunlu tutar)

Açılan sayfada **Geliştirici modu**nu aç → **Paketlenmemiş öğe yükle** → panodaki yolu yapıştır
(macOS: Cmd+Shift+G, Windows: Ctrl+V) ya da klasörü sayfaya sürükle. Sonra Fusion Browser
simgesine bir kez tıklayıp **Chrome iznini iste**yi onayla. Gerisi kendiliğinden bağlanır.

## Neden tam otomatik değil (dürüst özet)

| Yol | Durum |
|---|---|
| `--load-extension` ile Chrome'u eklentiyle başlatmak | Chrome 137'den itibaren resmî (markalı) Chrome'da kaldırıldı; ayrıca ayrı profil/oturum gerektirirdi. |
| Uzaktan hata ayıklama (`--remote-debugging-port`) ile eklenti yükletmek | Chrome 136'dan beri varsayılan profilde çalışmaz; çalışması için ayrı `--user-data-dir` gerekir, bu da gerçek oturumları/çerezleri kullanmamak demek. Kullanıcı profiline dokunmamak için kullanılmadı. |
| Kurumsal politika (`ExtensionInstallForcelist`) | Yönetilmeyen (MDM/alan adı dışı) macOS ve Windows'ta Web Store dışı eklentiler için yok sayılır; yönetici hakkı ve cihaz yönetimi ister. Kullanılmadı. |
| Chrome Web Store | Yayımlandığında gerçek tek tıkla kurulum olur; henüz yok. |
| Profile dosya yazarak eklenti eklemek | Chrome'un koruma imzalarını (Secure Preferences) bozar ve eklenti devre dışı kalır; oturumları riske atar. Yapılmaz. |

Bu tablodaki Chrome davranışları Chrome sürüm notlarına dayanır; kurulum sırasında ilgili
sürümde yeniden denenmedi. Fusion'ın otomatik yaptıkları (1-4) yukarıdaki testlerle doğrulanır,
tek manuel adım Chrome'un kendi onay ekranıdır.

## Güvenlik

- Fusion Chrome profil verisine yazmaz, çerez/oturum okumaz; yalnız eklentinin kurulu olup
  olmadığını `Preferences` dosyasından okur.
- Panoya yalnız eklenti klasörünün yolu yazılır.
- Eklenti sayfaları yalnız izin verdiğin sitelerde okur; ekran, fare ve klavye adımları panelin
  **denetim şeridinde** görünür ve izin kipine göre (Otomatik, Manuel, Plan…) onay ister.
