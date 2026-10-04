# Kalite fazları — ölçülen sonuç (4 Ekim 2026)

Kaynak plan: [2026-10-04-nemotron-kalite-arastirmasi.md](2026-10-04-nemotron-kalite-arastirmasi.md).
Model: `nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b`, öğretmen Gemini web "3.6 Flash".
Ölçüm: `python -m evals.kabul` — her alanın bağımsız denetçisi, ajanın söylediğine değil
üretilen çıktıya bakar. Ham kayıtlar: `~/Desktop/01-Projeler/fusion-kabul/taban/` (önce) ve
`sonra/` (sonra).

## Önce → sonra

| Alan | Önce (baz) | Sonra | Not |
|---|---|---|---|
| Site kopyası (sneaksup → WP/Woo) | 6/14 (17. koşu, 90 dk sınırında) | **14/14**, 25,6 dk | Görsel benzerlik 0,89. Aynı kodla bir koşu 13/14 (benzerlik eşiği). |
| HTML oyun | 6/7 | **7/7** (iki koşu) | Önceki "5/7" denetçinin ölçüm hatasıydı; denetçi düzeltildi, eski koşular yeniden puanlandı. |
| Remotion | 8/8 (11,0 dk) | 8/8 (7,7 dk) | Puan aynı, süre kısaldı. İki denetçi hatası düzeltildi (kare farkı eşiği, alt klasördeki kaynak); eski koşular yeniden puanlandı. |
| Kendini geliştirme | 6/6 | 6/6 | Değişmedi. |
| Animasyon | 6/8 | 6/8 – 7/8 (üç koşu) | Ölçülen iyileşme yok sayılır. Kalan madde: layout özelliği (`transition: width`) canlandırma. Kapanış kapısı eklendi; kapıdan sonraki iki koşu makine çökmesiyle yarıda kesildi, tam koşu ANIMASYON_BEKLENIYOR. |
| Tarayıcı (Fusion Browser) | 7/7 görünüyordu | **gerçekte geçmiyor** | Aşağıya bak. |

Tek koşuluk sonuçlar istatistik değildir; her alan en az üç kez koşulmadan "geçti" denmez.

## Tarayıcı alanı: baz ölçüm yanıltıcıydı

- `chrome_navigate` ve `browser_open` yerel adresleri (127.0.0.1) 25 Eylül'den beri
  reddediyor (`tools/web.py: url_block_reason`). Kabul fikstürü yerel adreste çalışıyor.
- Ajan tarayıcı aracı reddedilince işi `curl` ile bitirdi. Baz ölçümdeki 7/7 de böyle geçti.
- Bir koşuda model kendi başına `ngrok` kurdu ve `cloudflared tunnel` ile yerel sunucuyu
  herkese açık adrese bağladı.

Yapılanlar:

- Denetçiye iki madde eklendi: `tarayiciyla_yapildi` (form ve tablo istekleri gerçek tarayıcı
  kimliğiyle gelmeli) ve `tunel_acilmadi`. Eski koşular yeni denetçiyle 4/9 ve 8/9.
- Tünel açan komutlar (`ngrok`, `cloudflared tunnel`, `lt --port`, `ssh -R`) tehlikeli komut
  listesine girdi; artık her kipte kullanıcıya sorulur.

Karar (kullanıcı onayıyla uygulandı): tarayıcı araçları, kullanıcının kendi mesajında açıkça
yazdığı yerel adrese (`localhost` / `127.0.0.1` / `[::1]` + port) gider
(`tools/web.py: browser_block_reason`, `ToolContext.local_origins`). Diğer özel ağ adresleri,
metadata ucu, mesajda geçmeyen yerel portlar ve `web_fetch` / indirme / tarama araçları eskisi
gibi kapalıdır. Bu değişiklikten sonra tarayıcı alanı henüz yeniden ölçülmedi.

## Bu turda ayrıca düzeltilenler

- **Cevabın ezilmesi:** görev listesinde açık madde kalınca "bittiyse teyit et" notu altı kez
  gitti; modelin son kısa "tamamlandı" cevabı, fiyatı içeren asıl teslimin yerine geçti.
  Artık nottan önceki teslim korunur ve tur ilk teyitte biter (`loop.py`, `reflexion.keep_delivery`).
- **Oyun denetçisi:** `window.__GAME_STATE__` kancasını okur; yeniden başlatmayı oyun sonunda dener.
- **`play_probe`:** ajan oyunu başsız tarayıcıda oynatıp ölçer; `osascript` ile pencere
  sürmeye çalışması engellendi.

## Kalite kapısı

`ruff check` temiz, argümansız `mypy` temiz (462 dosya), `pytest` tam paket: SONUÇ_BEKLENİYOR.

## Açık kalanlar

1. Tarayıcı alanının yerel adres izninden sonra yeniden ölçülmesi (eklenti bağlıyken).
2. Animasyon alanı kapanış kapısıyla en az üç tam koşu.
3. Her alan için üçer koşu (istatistik); ikinci bir ücretsiz modelle genelleme koşusu.
4. MCP (Meta / Google Ads) tarafı bu ölçüm setinde yok.
5. Kabul koşuları terminal çekirdeğiyle yapıldı; masaüstü uygulaması + eklenti bağlıyken
   aynı set henüz koşulmadı.
6. Paket ve push yapılmadı; kurulu uygulama eski sürümde.
