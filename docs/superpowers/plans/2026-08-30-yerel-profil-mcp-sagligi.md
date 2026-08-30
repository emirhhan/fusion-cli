# Yerel Profil ve Gerçek MCP Sağlığı Uygulama Planı

> **REQUIRED SUB-SKILL:** Python tarafında `python-testing`, MCP tarafında `mcp-server-patterns`, React tarafında `react-patterns`, süreç sonunda `superpowers:verification-before-completion` kullan.

**Goal:** Sol panelde yerel bir kullanıcı/proje kimliği sunmak ve MCP bağlantılarının yalnız yapılandırılmış değil gerçekten başlatılıp araçlarının okunabildiğini göstermek.

**Architecture:** Fusion bulut hesabı varmış gibi davranılmaz. Profil yerel ayarlardan oluşur. MCP doğrulaması appserver isteğiyle `McpClient` üzerinden gerçek `initialize + tools/list` yapar; sonuç süreli cache ile UI'a taşınır. Anahtar veya ortam değeri sonuç nesnesine girmez.

**Tech Stack:** Python 3.11+, asyncio, MCP SDK, React 19, TypeScript, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-uygulama-gorsel-yenileme-ve-mcp-dogrulama-design.md`

**Global Constraints:** MCP komutunun kendisi ve argüman adları gösterilebilir; environment değerleri, tokenlar ve stderr içindeki sırlar redakte edilir. Doğrulama timeout'u 10 saniyedir ve yetkisiz işlem yapmaz.

## Task 1: MCP sağlık alan modeli ve appserver yolları

**Files:**
- Modify: `src/fusion_cli/appserver/connectors.py`
- Modify: `src/fusion_cli/appserver/session.py`
- Modify: `src/fusion_cli/mcp_bridge/client.py`
- Create: `tests/test_appserver_connectors.py`
- Test: `tests/test_mcp.py`

1. Aşağıdaki cevap sözleşmesini testte sabitle:
   `{"ad": str, "durum": "bagli|hata|zaman_asimi|kapali", "arac_sayisi": int, "gecikme_ms": int, "mesaj": str | null}`.
2. Başarılı gerçek stdio sunucusu, bulunmayan komut, initialize hatası ve timeout testlerini yaz; `pytest -q tests/test_appserver_connectors.py tests/test_mcp.py` ile kırmızı sonucu doğrula.
3. `McpClient` üzerine yan etkisiz `probe_server(name, timeout_seconds=10)` ekle. `asyncio.timeout` içinde context aç, initialize et, `list_tools` sayısını al ve mutlaka kapat.
4. `baglanti.dogrula` tek bağlantıyı; `baglanti.durum` tüm yapılandırılmış bağlantıları doğrulasın. Session içinde aynı config revizyonu için 30 saniyelik sonuç cache'i kullan; `yenile=true` cache'i atlasın.
5. Hataları kullanıcıya yararlı fakat sır içermeyen mesaja dönüştür; ham env ve tüm subprocess stderr'i asla cevapta taşıma.
6. Testleri çalıştır; commit: `feat(mcp): gerçek bağlantı sağlık doğrulaması ekle`.

## Task 2: Bağlantılar ayar yüzeyi

**Files:**
- Modify: `app/src/protocol/types.ts`
- Modify: `app/src/settings/Settings.css`
- Modify: `app/src/settings/Settings.test.tsx`
- Modify: `app/src/settings/Connectors.tsx`

1. Testlerde yükleniyor, bağlı + araç sayısı, timeout, hata, yeniden dene ve tümünü kontrol et durumlarını yaz.
2. Kırmızı test: `cd app && npm test -- Settings.test.tsx`.
3. Her MCP satırında yapılandırma durumunu sağlık durumundan ayır. “Bağlı” etiketi yalnız `baglanti.dogrula` başarılıysa gösterilsin.
4. Komut/argümanları açılır ayrıntıda göster; environment için yalnız anahtar adlarını göster ve değerleri `••••••` yap.
5. Bağlantı ekleme/silme sonrası ilgili sağlık cache'ini yenile.
6. Test/build; commit: `feat(app): MCP bağlantı sağlığını görünür yap`.

## Task 3: Yerel profil ve glossy sol panel

**Files:**
- Create: `app/src/profile/LocalProfile.tsx`
- Create: `app/src/profile/LocalProfile.test.tsx`
- Create: `app/src/profile/LocalProfile.css`
- Modify: `app/src/screens/Sidebar.tsx`
- Modify: `app/src/screens/Sidebar.css`
- Modify: `app/src/App.tsx`

1. Testlerde varsayılan “Yerel kullanıcı”, düzenlenebilir görünen ad, çalışma klasörü ve ayarlara geçiş davranışını yaz.
2. Profil verisini `fusion.local-profile.v1` altında yalnız cihazda sakla; e-posta/şifre formu ve sahte oturum durumu ekleme.
3. Sol paneli yarı saydam/glossy yüzey, doğru uygulama ikonları ve varsayılan açık sohbet geçmişiyle düzenle; daraltma kontrolünü koru.
4. `resume` satırlarında kaynak etiketlerini `[Claude]`, `[Codex]`, `[Hermes]` olarak göster; yalnız gerçekten bulunan kaynakları listele.
5. Test/build; commit: `feat(app): yerel profil ve glossy kenar çubuğu ekle`.

## Task 4: Güvenlik ve görsel kanıt

**Files:**
- Modify: `app/e2e/product-surfaces.visual.ts`
- Test: `tests/test_appserver_connectors.py`

1. Sahte token/env değerleriyle redaksiyon regresyon testi çalıştır; beklenen sonuç değerlerin hiçbir JSON veya hata metninde görünmemesidir.
2. Bağlı, hata ve timeout MCP satırlarının aday ekran görüntülerini üretip kullanıcıya göster.
3. Kullanıcı onayından sonra snapshot'ları kalıcılaştır; Python ve React testlerini tekrar çalıştırıp commit et: `test(mcp): bağlantı sağlık sözleşmelerini kilitle`.
