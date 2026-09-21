# Claude Paritesi — Faz 1 ve Faz 2 Sonuç Raporu (21 Eylül 2026)

Kaynak denetim: 17 Eylül 2026, 74 tur, 66 bulgu (`fusion-denetim.html`).
Planlar: `plans/2026-09-17-claude-paritesi.md`, `plans/2026-09-18-tek-ajan-dongusu.md`.
Aralık: `a0f37f5..d35b80f` (32 commit), dal `fusion-runtime-hardening-20260827-022831`.

## Faz 1 — Görünür hasarı durdur: TAMAM

| Bulgu | Durum | Commit |
|---|---|---|
| D1 cevabın biçimi siliniyor | Markdown olarak okunuyor | `15e8394` |
| B1 sohbet kipi dosya yazıyor | Sohbet turu çalışma alanına dokunmuyor | `09f6449` |
| A7 192 saniyelik boş bekleme | Kararlılık penceresiyle bitiş algısı | `f818530` |
| D2 sahte "doğrulanmadı" uyarıları | Gerçek kanıta bağlandı | `8d2a87c` |
| C1 varsayılan model iş yapamıyor | Kullanılamayan modelde yedeğe geçiş | `ca72015` |
| C2 görünmez Chrome CAPTCHA tetikliyor | Gizli pencere kipi + uygulamada seçim | `e711ffc`, `c7468c6`, `e3b85d7` |
| D5 zaman aşımından sonra kilitli oturum | İptalden sonra yeni mesaj kabul ediliyor | `328bc64` |
| D3 akış yok, iş sürerken yazılamıyor | Akış, kuyruk, Esc, canlı görev listesi | `fd199d4`, `d3ec3e9`, `dff3944` |
| H3 onayda değişiklik önizlemesi yok | Onay kartında diff | `f2513fb` |
| H6 bağlam göstergesi yok | Mesaj kutusunun yanında kalan bağlam | `34b925e`, `a0f37f5` |
| H9 sohbet başlığı üretilmiyor | İlk mesajdan deterministik başlık | `adcc0b1` |
| E1–E6 bağlayıcılar | Hata sınıflandırma, doğrulayarak kaydetme, havuz, katalog, "Bağlan" | `f40dc8b`, `f70cfd5`, `f40ecb2`, `bd97fae`, `04bd4a7`, `b974658` |
| F1–F3, B6 güvenlik | Proje dışı yol onayı, riskli komut aileleri, enjeksiyon işareti | `4636460`, `e5538d4`, `3df660e` |

## Faz 2 — Tek ajan döngüsü: TAMAM

| Görev | Sonuç | Commit |
|---|---|---|
| G1 tam metin eşleşmeli düzenleme + modele diff (A2) | `replace_range` kaldırıldı | `7c5fda7` |
| G2 onay reddi turu durdurur (B3) | Red = turun kararı | `ad7d50e`, `2db7584` |
| G3 plan adımları tek geçmiş, görünür geri alma (A4, A9, D4) | Adımlar konuşmayı paylaşıyor | `ded5907` |
| G4 yönlendirme modele bırakıldı (B2, A5, B5) | Kelime sınıflandırıcısı ve varsayılan plan motoru karar yolundan çıktı | `445425b` |
| G5 gözlem turunda yazma kapalı (B4, A13) | Yazmaya iten dürtmeler kaldırıldı | `eab84e7` |
| G6 başarı beyanı gerçek çıktıya bağlı (A1, A12) | Tur raporu araç kaydından üretiliyor | `282bc70` |

Gerçek koşularda çıkan ve aynı fazda düzeltilen yan bulgular: `515ac70`, `1c11d2e`,
`495c95b`, `4af3d1b`, `1562327`, `99e5007`, `14a6079`, `5b6f157`.

### Kök konuşmanın sıkıştırmada kaybolması (`d35b80f`)

Gerçek koşuda bulundu: "Hatırla: kod adı MAVİ-KEDİ" → uzun bir `/plan-yurut` turu →
"Kod adı neydi?" sorusunda cevap yanlış geldi. Kök neden plan geçmişi değil,
bağlam sıkıştırmasıydı: eşik aşılınca sistem mesajı ve kullanıcının kök turda
verdiği talimat dahil her şey tek bir olasılıksal özetleyici çağrısına emanet
ediliyordu. Artık kök tur (sistem mesajı + ilk kullanıcı turu) özetleyiciye hiç
girmiyor, birebir korunuyor.

## Kalite kapısı (21 Eylül)

- `ruff check .` temiz, `mypy` 350 kaynak dosyada temiz.
- Tam pytest takımı: 6 test düşüyor, **hepsi ortam kaynaklı**: OAuth dönüş portu
  8765'i bu makinede kullanıcının kendi `recv.py` süreci tutuyor. Aynı testler
  değişiklik öncesi commit'te (`a0f37f5`) de aynı hatayla düşüyor; gerileme değil.
  Port boşaldığında tekrar koşulmalı.
- Arayüz: `tsc --noEmit` temiz, vitest 628 test yeşil.

## Açık kalanlar

1. **Faz 3–7 yapılmadı:** çırak katmanı (ücretsiz API modelleri), öğretmen
   protokolü, dosya yükleme, bağlayıcı köprüsü, 74 turluk ölçüm seti.
2. `list_tools`, bağlantı kurulamamışsa `KeyError` fırlatıyor; anlaşılır hataya
   çevrilmeli (ortam hatası bunu görünür kıldı, kendisi eski bir davranış).
3. MCP'de gerçek tembel başlatma (araç listesinin diske önbelleklenmesi) yapılmadı.
4. `app/e2e/` hâlâ tip denetiminin dışında (bkz. `docs/BACKLOG.md`).
5. `step_verification.py` (810 satır) ve `appserver/session.py` (~1190 satır)
   RULES.md'deki dosya boyutu sınırının üstünde; bölünmeli.
6. Kurulu Fusion.app hâlâ eski sürüm; 0.4.0 paketlenip dağıtılmadı (G2 bulgusu).
