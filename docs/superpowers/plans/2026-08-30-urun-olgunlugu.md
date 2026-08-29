# Fusion Ürün Olgunluğu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Kullanıcının gerçek kullanımda bulduğu sekiz eksiği kapatmak. Kaynak: 30 Ağustos kullanım geri bildirimi.

**Architecture:** Yetenekler ÇEKİRDEKTE zaten var (web tarayıcı sağlayıcıları, motor
seçimi, oturum yönetimi); eksik olan bunların masaüstü protokolüne ve arayüze
açılmasıdır. Hiçbir madde yeni bir motor ya da yeni bir sağlayıcı mimarisi
gerektirmez — mevcut sözleşmeler genişletilir.

**Spec:** `docs/superpowers/specs/2026-08-29-tam-macos-uygulamasi-design.md` §10–13

## Global Constraints

- Sır değeri hiçbir protokol yanıtına, olaya ya da loga girmez.
- Web sağlayıcı girişi API anahtarı SORMAZ: ayrı tarayıcı penceresi açılır,
  kullanıcı orada giriş yapar, çerez izole profilde kalır (`web_browser.py`).
- Kullanıcıya görünen metinler Türkçe; tanımlayıcılar İngilizce.
- Her davranış önce başarısız testle sabitlenir.

---

### Görev 1: Web sağlayıcı bağlantısı (ANA TAŞ)

Kontrol panelinde dört web sağlayıcısı (ChatGPT, Claude, Gemini, Copilot) kendi
logosuyla ve kontrol merkezindekiyle AYNI akışla yer alır. Düz "API gir, kaydet"
kutusu KOYULMAZ — bu sağlayıcılar anahtar kullanmaz.

**Files:**
- Modify: `src/fusion_cli/appserver/control.py`
- Modify: `src/fusion_cli/appserver/session.py`
- Create: `app/src/control/WebProviders.tsx`, `.css`, `.test.tsx`
- Create: `app/src/brand/ProviderLogo.tsx`
- Modify: `app/src/control/ControlPanel.tsx`

**Interfaces:**
- `web.saglayicilar` → id, ad, bağlı mı, hesap, profil var mı, araç desteği, ölçüm geçti mi
- `web.giris` → tarayıcı penceresini aç, `pid` döndür
- `web.giris_durumu` → pencere hâlâ açık mı (kapanınca doğrulama kendiliğinden koşar)
- `web.dogrula` → bağlantıyı sına
- `web.olcum` → taklit araç yeteneğini ölç (dosya değiştirme kapısı)
- `web.kaldir` → oturumu ve profili sil

- [ ] Uçların sözleşmesini kırmızı testle yaz: bilinmeyen sağlayıcı çökertmez, sır sızmaz.
- [ ] Protokolü uygula; `gateway/app.py`'deki mantığı KOPYALAMA, ortak yere çıkar.
- [ ] Dört sağlayıcının logosunu SVG bileşen olarak ekle.
- [ ] Paneli bağla: kart + durum + "Giriş yap" + otomatik doğrulama + ölçüm kapısı.

### Görev 2: Sohbet ve Kod ayrımı

Kullanıcının istediği ayrım motor değil ÇALIŞMA KİPİDİR:
- **Sohbet:** tek yapay zeka, agent kipinde; görsel üretimi dahil her şey burada da
  yapılabilir; dosya sistemine odaklanmaz.
- **Kod:** model seçilebilir; proje köküne bağlı çalışır.

**Files:** `src/fusion_cli/appserver/session.py`, `app/src/App.tsx`, `app/src/screens/Sidebar.tsx`

- [ ] "merhaba" gibi bir mesajın proje taramasını TETİKLEMEDİĞİNİ testle sabitle.
- [ ] Kip seçimini protokole ve arayüze aç; varsayılan Sohbet.

### Görev 3: Çalışma dizini

`std::env::current_dir()` GUI'de `/` döner; her sohbet kök dizini listeliyordu.

**Files:** `app/src-tauri/src/session_manager.rs`, `app/src/App.tsx`

- [ ] Kök verilmediğinde ev dizinine düşüldüğünü, ASLA `/` olmadığını testle sabitle.
- [ ] Proje seçiciyi arayüze bağla; son proje hatırlansın.

### Görev 4: Oturum yönetimi

- [ ] Sohbet silme (onaylı, geri alınamaz olduğu söylenir).
- [ ] Sohbetleri projeye göre gruplama; proje altında sohbet açma.

### Görev 5: Gerçek Ayarlar ekranı

Kontrol Paneli'nden AYRI: tema, bağlayıcılar, kullanım durumu, sağlık, hesap.

### Görev 6: Kontrol paneli derinliği

Web panelindeki ayrıntı düzeyine çıkar: ana model değiştirme, kök ayarlama,
sağlayıcı görünümü.

### Görev 7: Responsive

- [ ] Daraltma/genişletmede kaybolan butonları bul ve düzelt; görsel senaryo ekle.

### Görev 8: Dersler

Altı-yedi sayfalık, önizlemeli, gerçekten öğreten içerik.

## Çıkış Kriterleri

- [ ] Web sağlayıcılar panelden anahtar sorulmadan bağlanır ve bu akış hatasız çalışır.
- [ ] Boş sohbette "merhaba" dosya taraması başlatmaz.
- [ ] Hiçbir sohbet `/` dizininde açılmaz.
- [ ] Sohbet silinebilir ve projeye bağlanabilir.
- [ ] Ayarlar ve Kontrol Paneli ayrı, ikisi de gerçek veriye bağlı.
- [ ] Dar ve geniş ekranda hiçbir kontrol kaybolmaz.
