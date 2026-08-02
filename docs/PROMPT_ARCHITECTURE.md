# Prompt Mimarisi

## Katmanlı birleştirme

Agent'ın sistem promptu tek devasa metin değildir; `_initial_messages`
(`engines/agent/loop.py`) katmanları sırayla birleştirir:

```
SYSTEM_PROMPT (system.md)          # kimlik + ton + çalışma yöntemi + doğrulama + güvenlik
  + PLAN_MODE_PROMPT (plan_mode.md)  # yalnızca plan modunda: mutasyon yasağı
  + extra_system                     # ders belleği + uzmanlık (skill) + makro kipi
```

Prompt metinleri koda gömülü değildir; `engines/agent/prompts/*.md` altında paket
verisi olarak tutulur (RULES: uzun prompt metinleri ayrı dosyada) ve import anında
yüklenir. `pyproject.toml`'daki `package-data` bunları wheel'e dahil eder;
`test_packaging` ve clean-install smoke bunu doğrular.

## Davranış güvenceleri (regression testleri)

Prompt metni üründür: bir güvence kaybolursa agent sessizce kötüleşir. `test_prompts.py`
davranışsal anahtarları kilitler (birebir cümleyi değil):

- Dosyayı düzenlemeden önce **oku** (kör değişiklik yasak).
- İşi test/lint/build ile **doğrula**; varsayımda bulunma.
- Dosya yolu / fonksiyon adı **uydurma**.
- Araç çağırmadan durma (sadece açıklayıp bırakma).
- Yıkıcı komutta (rm -rf) önce dur.
- Plan modunda mutasyon yasağı prompt'a eklenir; kapalıyken eklenmez.
- Ders/uzmanlık bloğu sistem promptuna katılır (compaction'da kaybolmaz).

## Neden büyük bir composer ağacı kurulmadı

Master prompt çok dosyalı bir `prompts/` ağacı (identity/behavior/coding/tools/…)
önerir. Mevcut prompt zaten bölümlüdür ve **ölçülmüş davranışlar** taşır; onu daha
ayrıntılı bir ağaca yeniden yazmak, çalışan bir sistemi ikinci bir yol olarak yeniden
kurmak olurdu (RULES) ve agent'ın çekirdek davranışında regresyon riski taşırdı.
Bunun yerine mevcut katmanlı birleştirme korunmuş, davranış güvenceleri **test altına
alınmıştır**. Daha ince katmanlama, gerçek bir ihtiyaç doğduğunda yapılabilir.
