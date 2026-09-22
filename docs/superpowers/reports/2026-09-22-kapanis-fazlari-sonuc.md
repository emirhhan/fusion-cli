# Kapanış Fazları Sonuç Raporu (22 Eylül 2026)

Plan: `plans/2026-09-22-kapanis-fazlari.md`. Kaynak: 17 Eylül Claude paritesi
yol haritasının Faz 7'si + roadmap'te olmayan, kullanıcının asıl hedefini bloke
eden ölçülmüş hatalar.

## Faz A — Depo haritası: ölçülen 164,6 dakika, 0,38 saniyeye indi

`core/repo_map.py` her kök agent turunda çalışıyor ve Fusion'ın gerçek boyutta
hiçbir depoda (kendi deposu dahil) çalışmasına izin vermiyordu.

| Ölçüm (fusion-cli deposunun kendisi) | Önce | Sonra |
|---|---|---|
| Referans sayımı karmaşıklığı | `O(sembol × toplam_karakter)` | `O(toplam_karakter)` |
| Benzersiz sembol × karakter | 13.889 × 75.069.360 | tek kelime geçişi |
| **Harita üretim süresi** | **164,6 dk (ölçüldü)** | **0,38 sn** |
| Önbellekten | — | 0,029 sn |
| Taranan dosya | 4.373 | 811 |

Üç ayrı hata vardı:

1. **Karesel referans sayımı.** Her benzersiz sembol için ayrı regex derlenip
   BÜTÜN dosya metinleri baştan taranıyordu. 50 sembol 35,56 saniye sürdü;
   13.889 sembol için ölçülen tahmin 164,6 dakika. Artık her dosya bir kez
   kelimelere ayrılıp `Counter` ile sayılıyor. Davranış eşdeğer: tanım adları
   her zaman `[A-Za-z_]\w*` biçiminde, `oran2`/`_oran` iki yolda da eşleşmiyor.

2. **Harita `.gitignore`'daki üretilmiş ağaçla doluyordu.** Haritanın İLK ALTI
   satırı `app/src-tauri/resources/runtime/unpacked/` altındaki paketli runtime
   kopyasından geliyordu — litellm ve httpx sembolleri; projenin kendi kodu
   listeye hiç giremiyordu. O ağaç `fusion_cli`'ın bir kopyasını da taşıdığı için
   her sembol iki kez sayılıyordu. Artık dosya listesi `git ls-files -z --cached
   --others --exclude-standard` ile alınıyor (0,014 sn); git yoksa budamalı elle
   yürüyüşe düşülüyor.

3. **Aynı ad bütün bütçeyi yiyordu.** Sıralama sembolün referans sayısına baktığı
   için haritanın ilk dokuz satırı dokuz ayrı dosyadaki `config` fixture'ıydı.
   `_MAX_PER_SYMBOL = 2` eklendi (`_MAX_PER_FILE` ile aynı gerekçe).

Ayrıca harita artık dosya imzasına (sayı + toplam boyut + toplam mtime) göre
önbelleğe alınıyor — `repo_context.py`'ın docstring'i zaten "turdan tura aynıdır"
diyordu ama önbellek yoktu. Patolojik depo için dosya/karakter tavanı var ve
tavan aşılırsa harita KISMİ olduğunu söylüyor.

**Canlı doğrulama:** `fusion agent` fusion-cli deposunun kendi kökünde (14 GB,
156.002 yol) çalıştırıldı ve **3 dakika 3 saniyede** doğru cevabı verdi. Proje
belleğindeki "canlı test her zaman izole bir scratch dizininde yapılmalı" kuralı
artık gerekmiyor.

## Faz B — MCP ve bağlayıcılar

1. **`list_tools` ham `KeyError` fırlatıyordu** (Faz 1/2 raporunun açık kalanlar
   md. 2). Bağlantı kurulamamışsa kullanıcı sunucu adından ibaret bir hata
   görüyordu. `McpNotConnectedError` eklendi; mesaj sınıflandırılmış bağlantı
   hatasını (`_statuses`) taşıyor ve "tanımlı değil" ile "bağlanamadı"yı ayırıyor.

2. **Barındırmalı connector'lar kopya korumasının DIŞINDAYDI.** `mcp_servers`
   `unique_configs` ile korunuyordu, `hosted_connectors` korunmuyordu.
   `hosted_identity` / `unique_hosted_configs` eklendi (sağlayıcı + hesap + normalize
   URL); doğrulanmış kayıt doğrulanmamış kopyasına yenilmiyor. Ekleme yolu da
   artık yalnız ada değil ADRESE bakıyor.

**Kullanıcının gerçek yapılandırmasında ölçülen durum** (dokunulmadı):

| Ad | Adres | Durum |
|---|---|---|
| `META ADS` | `https://mcp.facebook.com/ads` | doğrulanmamış |
| `Meta Ads` | `https://mcp.facebook.com/ads` | **yukarıdakinin kopyası** |
| `meta ads` | `https://mcp.facebook.ads.com` | **ölü adres** — DNS çözmüyor |

Üçüncü kayıt bir yazım hatası: doğru adres `mcp.facebook.com/ads`, yazılan
`mcp.facebook.ads.com` hiç çözülmüyor (`socket.gethostbyname` → bilinmeyen ad).
Yeni ayıklama ilk ikisini tek kayda indiriyor; üçüncüsü farklı adres olduğu için
KOPYA SAYILMIYOR ve ayakta kalıyor — silinmesi kullanıcının kararı.

## Faz C — Faz 7: ölçüm

**Kaynak kaybı (dürüstlük notu):** 74 turluk denetim dosyası `fusion-denetim.html`
artık ne depoda, ne diskte, ne git geçmişinde. Arandı, bulunamadı. Set o turların
birebir kopyası DEĞİL; hayatta kalan bulgu kimliklerinden (A/B/C/D/E/F/H serileri)
ve Faz 1/2 düzeltme tablosundan yeniden kuruldu.

Eklenenler:

1. **Yalan başarı ölçümü.** Agent'ın kendi bitiş beyanı (`AgentOutcome.ok` +
   adım sınırına dayanmama) ölçüm hattına taşındı; `TaskResult.false_success`
   "agent bitti dedi ama ölçüt tutmadı" demektir. Kota yüzünden ölçülemeyen tur
   yalan başarı SAYILMAZ. Bu metrik bugüne kadar HİÇ ölçülmüyordu, oysa
   roadmap'in kabul eşiği onu sıfır istiyordu.

2. **Olumsuz ölçütler.** `file_unchanged` ve `workspace_unchanged` eklendi.
   Paritenin en pahalı bulguları ("sohbet kipi dosya yazıyor" B1, "gözlem turunda
   yazma" B4, "onay alınmadan iş" F1-F3) olumlu ölçütle ölçülemiyordu: hiçbir
   dosya beklenmediği için `file_changed` doğru davranışı da yanlış davranışı da
   aynı gösteriyordu.

3. **`evals/suite/parite.yaml`** — 14 gerileme senaryosu, her biri düzelttiği
   bulgunun kimliğini taşıyor. Arayüz bulguları (H1-H13) bilerek dışarıda:
   akış, Esc ile kesme ve diff önizlemesi headless koşucuyla ölçülemez.

4. **`evals/acceptance.py`** — roadmap'in dört eşiği makine-okunur oldu (doğru
   tur oranı %70 üstü, yalan başarı 0, oturum tamamlanması tam, ortalama tur
   90 sn altı). `python -m evals run --enforce` eşiğin altında sıfırdan farklı
   çıkış kodu döndürüyor; eşik artık yalnız raporun dipnotunda yazmıyor.

## Roadmap dışı, canlı koşuda bulunan iki hata

### `/goal` kipi TUI'de düşüyordu

`cli/repl/tui_loop.py` turu başlatırken makro kipinin yalnız `workflow` alanını
geçiriyordu. `/goal` çağrıldığında kipin sistem promptu ("pes etme, `ask_user`
ile müdahale iste") ve yükseltilmiş adım sınırı (100) sessizce düşüyordu. Düz
konsol yüzeyi (`loop.py`) üçünü de geçiriyordu — iki yüzey ayrışmıştı.

### Yedeğe düşen tur salt-okunur kilitli kalıyordu

Tur başında yetenek kapısı YAPILANDIRILMIŞ modele göre kapanıyor, sonra zincir
başka bir modele düşüyor ve kilit turun sonuna kadar kalıyordu. Kullanıcının
kendi kurulumunda ölçüldü: `chatgpt_web/main` insan doğrulamasına takıldı, zincir
`nvidia_nim/nemotron-3-ultra-550b-a55b`'ye düştü, tur SALT-OKUNUR bitti — oysa
engelin gerekçesi ("chatgpt_web taklit aracı ölçülmedi") artık işi yapan modele
ait değildi ve o model yazabiliyordu. Kullanıcı hiçbir dosyanın neden
yazılamadığını göremiyordu.

`refresh_mutation_policy` eklendi: her model çağrısından sonra, turu GERÇEKTE
karşılayan model (`ModelResult.served_by`) yetenek kapısını tazeliyor. Kapı
yalnız AÇILIR, hiç kapanmaz — turun ortasında aracı elinden alınan model yarım
iş bırakır. Kip kaynaklı engel (sohbet, gözlem) buraya hiç girmiyor:
`mutation_blocked_by_capability` bayrağı ikisini ayırıyor.

## Meta Ads için ChatGPT'ye HİÇ ihtiyaç olmayan yol (kod okunarak doğrulandı)

Bugün Meta Ads, ChatGPT web oturumunun üstünden giden bir `hosted_connector`
olarak tanımlı — bu yüzden ChatGPT'nin CAPTCHA'sı reklam işini de kilitliyor.
Oysa Fusion'da **doğrudan** yol zaten var ve çalışıyor:

- `mcp_bridge/client.py:174` — `token_env` doluysa OAuth tamamen ATLANIR;
  giriş penceresi açılmaz, her turda yeniden yetkilendirme denenmez.
- `mcp_bridge/transport.py:resolve_bearer_headers` — token
  `Authorization: Bearer …` başlığına çevrilir ve `streamablehttp_client`'a
  verilir.

Bu, proje belleğindeki ölçümle birebir uyuşuyor: `mcp.facebook.com/ads` dinamik
istemci kaydını (DCR) reddediyor ama
`/.well-known/oauth-authorization-server/ads` metadatası
`bearer_methods_supported: ["header"]` diyor — hazır token başlıkla kabul edilir.

Pratik karşılığı: Business Manager'da süresi dolmayan bir **System User token**
üretip bağlantıyı masaüstü panelinden `https://mcp.facebook.com/ads` adresiyle
ve token'la eklemek yeterli. Token `config.yaml`'a YAZILMAZ; ad üzerinden
türetilen bir ortam değişkenine bağlanır (`appserver/connectors.py:token_env_name`)
ve hiçbir yanıtta değeri görünmez (yalnız `token_var: true`).

**Boşluk (backlog):** `fusion mcp-add` yalnız stdio sunucusu ekleyebiliyor
(`name command args`); HTTP + token yolu YALNIZCA masaüstü panelinde var.
Terminalden aynı bağlantıyı kurmak bugün mümkün değil.

## Kullanıcı eylemi gereken, kodla çözülemeyen

1. **ChatGPT web oturumu insan doğrulaması bekliyor.** Canlı koşuda görüldü:
   `authentication: ChatGPT Web (Plus/Pro)`. CAPTCHA'yı otomatik aşmak yasak.
   Tek yol: `python -m fusion_cli.providers.web_login chatgpt_web main`.
   Bu tamamlanana kadar birincil model her turda yedeğe düşüyor.

2. **Ölü bağlayıcı kaydı.** `meta ads` → `mcp.facebook.ads.com` silinmeli;
   kullanıcının verisi olduğu için dokunulmadı.

## Kapsam dışı bırakılanlar (gerekçesiyle)

`RULES.md`'nin 400 satır sınırını aşan 11 modül var (`loop.py` 2357,
`web_browser.py` 2343, `gateway/app.py` 1433, `plan_runner.py` 1371,
`session.py` 1257, `memory/seed.py` 1173, `renderer.py` 901, …). Gerçek bir borç
ama kullanıcının hedeflerinin hiçbirini bloke etmiyor; bu oturumda bölünmedi.

## Kalite kapısı

`ruff check .` temiz · `mypy` 357 kaynak dosyada temiz · tam `pytest` takımı
yeşil. **Düzeltme:** önceki fazlar `mypy src` koşmuş (318 dosya); `pyproject.toml`
mypy'ye `src`, `evals`, `prompt_opt`, `desktop_build` veriyor. Doğru komut
argümansız `mypy` — bu raporun ölçümü onunla alındı.
