# Fusion macOS Dersler ve Yayın Kapısı — G/H Aşaması Sonuç

## Teslim edilenler

### Dersler (G)

- Tasarım §12'deki sekiz ders protokolde veri olarak durur: `ders.listele` ve
  `ders.getir`. Bilinmeyen ders kimliği süreci çökertmez, anlaşılır hata döner.
- Sol navigasyondaki "Dersler" satırı artık ölü bağlantı değil; gerçek ekrana gider.
- Ders adımı hiçbir şey ÇALIŞTIRMAZ. "Bunu dene" ya var olan bir sekmeyi öne
  getirir ya da composer'a hazır görev metnini koyar; göndermeye ve onaylamaya
  kullanıcı karar verir. Mevcut onay ve geri alma sözleşmesi değişmedi.
- İlerleme yalnız güvenli metadata olarak saklanır: `{surum, ilerleme:{ders: adım}}`.
  Mesaj, dosya içeriği, PID ve hassas değer kayda GİRMEZ; bu bir testle sabittir.
- Bozuk, eski ya da erişilemez kayıt uygulamayı düşürmez; boş ilerlemeye döner.

### Güvenlik (H)

- Gateway'in `Host` denetimindeki test kaçışı kapatıldı. `Host: local` daha önce
  koşulsuz kabul ediliyordu — ASGI birim testleri `http://local` tabanıyla
  konuştuğu için. "local" adını 127.0.0.1'e çözen bir ağda bu, DNS-rebinding
  korumasını atlatırdı. Testler artık gerçek yerel adla konuşuyor ve `local`
  başlığının `421` ile reddedildiği ayrı bir regresyon testiyle kilitlendi.
- `npm audit`: 0 açık.

## Doğrulama

Sayılar gerçekten çalıştırılmış komutlardan alınmıştır.

- Kök kapısı (`make check`): Ruff temiz, mypy temiz, 2.560 Python testi ve
  105 kilitlenme/sözleşme testi geçti.
- Masaüstü kapısı (`make app-check`): 125 React testi, TypeScript/Vite
  üretim derlemesi, Clippy ve 34 Rust testi geçti.
- Görsel kapı (`make app-visual`): 29 senaryo geçti; üçü yeni ders
  senaryosu (açık, koyu, 920 px).
- Büyük konuşma: 800 mesajlı konuşma 1500 ms eşiğinin altında çizildi (ölçülen
  değer tipik olarak eşiğin onda biri).
- Çevrimdışı açılış: paketli çalışma zamanının sağlık denetimi sözleşme gereği
  ağ çağrısı yapmaz ve model çağırmaz; `tests/test_runtime_health.py` bunu sabitler.

## Görsel denetimde bulunan ve düzeltilen gerçek kusurlar

1. Ders ekranının CSS'i var olmayan tasarım tokenlarına (`--surface-subtle`,
   `--border-default`) bağlanmıştı; geçersiz `var()` bildirimleri düştüğü için
   kartların zemini ve kenarlığı hiç çizilmiyordu. Gerçek tokenlara bağlandı.
2. `.app-shell__main` bir flex kapsayıcı; ders bölümü `flex: 1` almadığı için
   liste ~446 px'e sıkışıp tek sütuna düşüyordu (tarayıcıda ölçüldü).
3. Grid'in varsayılan `align-content: stretch` değeri artan dikey boşluğu
   satırlara dağıtıp kartları gereksiz yere uzatıyordu.

## Yöntem notu

`playwright test --update-snapshots`, fark `maxDiffPixelRatio` toleransının
altında kaldığında PNG'yi YENİDEN YAZMAZ. Bu yüzden CSS düzeltmelerinden sonra
dar ekran görseli eski hâlini gösterdi ve gözle denetim yanlış sonuca götürdü.
Doğrusu: görsel bir kusuru düzelttikten sonra ilgili snapshot dosyasını silip
yeniden üretmek.

## Dağıtım

- `Fusion_0.3.0-alpha.1_aarch64.dmg` — 157 MiB, `Fusion.app` 166 MiB.
  Paylaşılabilir kopya: `~/Desktop/Fusion-0.3.0-alpha.1-Apple-Silicon.dmg`
  SHA-256: `eced487844797f8646351af0cf040ff0fbf01bb1573a222bbe83cea211ecbc7a`
- Paket sıfırdan üretildi (`make app-package`): PyInstaller çalışma zamanı, deterministik
  arşiv, paket içi çalışma zamanı smoke'u, Tauri release bundle ve DMG.
- Temiz HOME doğrulaması geçti: `Uygulama paketi doğrulandı: 0.3.0a1 · aarch64-apple-darwin`
  (ilk açılışta çalışma zamanı kuruldu, ikinci açılışta yeniden kurulmadı).

Apple Developer hesabı olmadığı için paket imzasız ve notarize DEĞİLDİR. Başka bir
Mac'te ilk açılışta Finder'da sağ tık → **Aç** gerekir; yönerge `app/KURULUM.md`
dosyasında.

**Intel (x86_64) paketi bu makinede üretilemedi.** Sessizce atlanmadı: bu Mac'te
Intel hedefli Python ve Rust zinciri kurulu değil. Paket yalnız Apple Silicon
(M1/M2/M3/M4 ve sonrası) içindir. Intel'li bir arkadaşın kullanabilmesi için ya
Intel bir Mac'te ya da CI'daki x86_64 işinde derlenmesi gerekir; CI tanımı
`9b15b5a` ile eklenmişti.

## Kalan açık maddeler

- `healthy_version`, eski kurulu sürümlerin giriş noktası adını GÜNCEL manifestten
  okuyor (eski manifestler saklanmıyor). Tek-ikili modelde sorun değil; giriş
  noktası adı sürümler arası değişirse rollback kırılır.
- Intel paketi ve iki mimarili doğrulama (yukarıdaki sebeple).
