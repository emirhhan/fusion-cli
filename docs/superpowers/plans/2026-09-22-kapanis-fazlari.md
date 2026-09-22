# Kapanış Fazları — Claude Paritesinin Gerçek Engelleri (22 Eylül 2026)

Kaynak: 17 Eylül roadmap'i (`2026-09-17-claude-paritesi.md`) Faz 1-6 tamam, Faz 7
açık. Bu plan Faz 7'yi kapatır ve ondan ÖNCE, roadmap'te olmayan ama kullanıcının
asıl hedefini ("Fusion, Fusion'ı baştan yazabilmeli; reklamları yönetebilmeli;
GATE HOLDING gibi bir tarayıcı işini yapabilmeli") bloke eden ölçülmüş hataları
düzeltir.

## Faz A — Depo haritası: kendi deposunda çalışabilme  [ENGEL]

**Ölçülen hata (22 Eyl, bu makinede, fusion-cli deposunun kendisinde):**

| Ölçüm | Değer |
|---|---|
| `rglob("*")` yol sayısı | 156.002 |
| Filtrelenmiş kaynak dosya | 4.789 |
| Toplam kaynak karakter | 75.069.360 |
| Benzersiz sembol | 13.889 |
| 50 sembolün referans sayımı | 35,56 sn |
| **13.889 sembolün tahmini süresi** | **164,6 DAKİKA** |

Kök neden `core/repo_map.py:_reference_counts`: her benzersiz sembol için ayrı
regex derleyip BÜTÜN dosya metinlerinde `findall` çalıştırıyor. Karmaşıklık
`O(sembol × toplam_karakter)` = 13.889 × 75 milyon karakter.

Bu, ürünün kimliğini doğrudan vuruyor: harita her kök agent turunda üretiliyor
(`engines/agent/repo_context.py`), yani Fusion gerçek boyutta HİÇBİR depoda
çalışamıyor — kendi deposu dahil. Proje belleğindeki "25+ dakika takılıyor,
canlı test izole scratch dizininde yapılmalı" notu bu hatanın semptomuydu;
kök neden şimdiye kadar aranmamıştı.

**Yapılacak:**

1. Referans sayımı tek geçişe indirilir: her dosya BİR KEZ kelimelere ayrılır,
   `Counter` ile sayılır, semboller bu sayaçtan okunur. `O(toplam_karakter)`.
2. Dizin budama yürüyüş sırasında yapılır (`os.walk` + `dirnames` filtresi),
   böylece `.worktrees` (3,0 GB) ve `node_modules` (185 MB) ağacına HİÇ girilmez.
   Bugün `rglob` içeri giriyor, sonra yolu atıyor.
3. Harita (kök, parmak izi) başına önbelleğe alınır. `repo_context.py` docstring'i
   zaten "dosyalar değişmedikçe metni turdan tura aynıdır" diyor ama önbellek YOK;
   her tur sıfırdan hesaplanıyor.
4. Patolojik depo için üst sınır: dosya/karakter tavanı aşılırsa harita kısmi
   üretilir ve bunu SÖYLER — sessizce asılı kalmaz.
5. Testler: sayım eşdeğerliği (eski/yeni aynı sırayı üretir), budama, önbellek
   geçersizleşmesi, tavan davranışı. Kabul: fusion-cli deposunda harita < 10 sn.

## Faz B — MCP ve bağlayıcılar: reklam yönetimi yolu  [ENGEL]

Faz 1/2 raporunun "Açık kalanlar" listesinden, kullanıcının reklam hedefini
doğrudan etkileyen maddeler:

1. `list_tools` bağlantı kurulamamışsa `KeyError` fırlatıyor (rapor md. 2) —
   anlaşılır hataya çevrilir.
2. Araç listesi diske önbelleklenmiyor; her agent turu tüm MCP sunucularına
   yeniden bağlanıyor (rapor md. 3, proje belleği "Açık kalanlar"). Tembel
   başlatma + önbellek.
3. Kullanıcının gerçek `config.yaml`'ında aynı Meta Ads MCP için iki yinelenen
   kayıt var ("META ADS" / "Meta Ads", ikisi de `verified: false`). Faz 6 raporu
   bunu buldu ama kullanıcı verisine dokunmadı. Yinelenen kayıtları TESPİT edip
   kullanıcıya bildiren, onayla temizleyen yol eklenir.
4. Meta Ads MCP'ye Bearer token ile bağlanma yolu doğrulanır. Altyapı zaten var
   (`mcp_bridge/transport.py:resolve_bearer_headers`, `config.token_env`);
   eksikse belgelenir/kapatılır. (Meta'nın DCR'ı reddettiği, ama
   `bearer_methods_supported: ["header"]` dediği ölçülmüş bir gerçektir.)

## Faz C — Faz 7: ölçüm seti

Roadmap'in kabul eşiği: doğru tur oranı %70 üstü, **yalan başarı 0**, uzun
oturumda 21/21 tamamlanma, ortalama tur < 90 sn.

**Engel:** 74 turluk kaynak denetim dosyası (`fusion-denetim.html`) artık ne
depoda, ne diskte, ne git geçmişinde. Aranıp bulunamadı.

**Karar (varsayım olarak ilan ediliyor):** senaryo seti, hayatta kalan kayıttan
yeniden kurulur — roadmap'teki bulgu kimlikleri (A1-A13, B1-B6, C1-C10, D1-D5,
E1-E7, F1-F3, H1-H13) ve Faz 1/2 sonuç raporunun düzeltme tablosu. Her düzeltilmiş
bulgu için, o bulguyu YENİDEN ÜRETECEK bir gerileme senaryosu yazılır. Bu, 74 turun
birebir kopyası değildir; ama ölçtüğü şey aynıdır: düzeltmeler gerçekten tutuyor mu.

1. `evals/suite/parite.yaml` — bulgu kimliğine bağlı gerileme senaryoları.
2. Eksik metrikler eklenir: `evals/metrics.py` bugün yalan başarıyı ÖLÇMÜYOR
   (`false_success`: agent "bitti" dedi ama ölçüt tutmadı), uzun oturum
   tamamlanmasını ve tur süresi eşiğini de raporlamıyor.
3. Kabul eşikleri `evals/` içinde makine-okunur hale gelir; koşu eşiği geçmezse
   çıkış kodu sıfır DEĞİLDİR.

## Faz D — Paketleme ve dağıtım

Kurulu `Fusion.app` hâlâ eski çalışma zamanı; Faz 1-6'nın hiçbiri kullanıcının
gerçekten çalıştırdığı uygulamada YOK. Sürüm `0.4.1`. Bu faz bitmeden kullanıcı
yapılan işin hiçbirini kullanamaz.

## Kapsam dışı (gerekçesiyle)

`RULES.md` 400 satır sınırını aşan 11 modül var (`loop.py` 2357, `web_browser.py`
2343, `gateway/app.py` 1433, `plan_runner.py` 1371, `session.py` 1257, …). Bu
gerçek bir borç ama kullanıcının hedeflerinin HİÇBİRİNİ bloke etmiyor ve bu
oturumun bütçesini yer. `docs/BACKLOG.md`'ye net kapsamla yazılır, bu fazlarda
bölünmez.

## Kalite kapısı

Her faz sonunda `ruff check` + `mypy src` + `pytest`. Üçü temizse Türkçe
conventional commit. Başlangıç ölçümü (22 Eyl): ruff temiz, mypy 318 dosyada
temiz, pytest koşuyor.
