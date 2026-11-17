# Korunan başlangıç talimatlarının bağlam bütçesi

5 Kasım 2026 düzeltmesi: otomatik özetleme eşiği, sıkıştırıcının birebir koruduğu başlangıç bölümü dışındaki geçmişi ölçer. Korunan bölüm `history.task_anchor_length` ile tanımlanır; talimat başlıklarını tanıyan ikinci bir liste yoktur. Sistem dışındaki bu bölümün boyu, yumuşak geçmiş eşiğine eklenir. Hem çağrı öncesi hem tur sonu aynı hesabı kullanır; çağrı öncesi koruma ölçümü ve thrash denetimi de aynı eşikle çalışır.

## Kanıt ve sınırı

`configured-default-d609/context-threshold-reconstruction.json`, kaynak/yapılandırmadan yeniden kurulan eşikte Gemini web için 24.000 karakter, bilinmeyen model penceresi ve tahmini bütçe bildiriyor. İlk gerçek istekte sistem 10.629, sistem dışı geçmiş 51.516, toplam mesajlar 62.145 karakterdi; araç şemaları ayrıca taşınıyordu. Bu dosya kayıp canlı olayın tam yükü değildir. Sağlayıcının ilk isteği kabul edip araç çağrısı döndürmesi, 24.000 karakterin doğrulanmış fiziksel kapasite sayılmaması gerektiğini ayrıca gösterir. QA'nın ilk web aramasını reddettiği yönündeki değerlendirme ayrı harness hatasıdır.

Kaynakta önceki `history_chars` hesabı yalnız sistem mesajını çıkarıyordu. Sıkıştırıcı ise ilk gerçek kullanıcı görevine kadarki başlangıç notlarını da değişmez tutuyor. Dolayısıyla başlangıç notu tek başına 24.000'i geçince eski araç çıktıları temizlense ve özet üretilse bile ölçüm bu eşiğin altına inemiyordu. Bu, canlı koşudaki her adımın birebir yeniden oynatılması değildir; aynı mekanizmanın kontrollü tekrarıdır.

`tests/test_protected_context_budget.py` gerçek talimat yükleyicisiyle geçici ev dizininde 50 KB üstü sentetik CLAUDE.md yükler. Gerçek AgentLoop ve WebProviderAdapter üzerinden yerel dosya okuma Webframe'leri üretir. Eski kod dört okumayı tamamlayamadan başarısız olur; yeni kod kısa çıktıları özetlemeden tamamlar. Çıktılar büyüdüğünde gerçek sıkıştırma devreye girer. Her sağlayıcı isteğinde ve devam turunda talimatların bütün baytları korunur. Özel kullanıcı talimatları testlere kopyalanmamıştır.

## Katı sınırlar

Bilinen model penceresinden sistem/çıktı/araç payı düşülür. Küçük pencerelerde rezerv, mevcut `_base_budget` ve `chars_for_window` hesabıyla aynı şekilde pencerenin yarısıyla sınırlanır; aksi halde 8K/16K modellerde geçerli küçük istemler de negatif kalan kapasite nedeniyle reddedilirdi. 8K, 16K ve 32K için hem küçük geçerli önek hem gerçekten büyük korunan önek kontrolleri bulunur. Sağlayıcının gerçek bağlam taşmasından öğrenilen eşik, önceki gibi sistem dışı geçmişin tamamına uygulanır; korunan bölüm payı bu sınıra eklenmez. Katı sınır korunan bölümden küçükse mevcut `ConfigError` ile açıkça durulur. Yalnız hatayı gizlemek için 4.000 karakterlik tabana yükseltilmez ve boşuna özetleme yapılmaz. Desktop istek sınırında hata yanıtı üretilmesi, çalışan tur sahipliğinin bırakılması ve sıfır sağlayıcı çağrısı ayrıca sınanır.

Araç argümanları ve görsel tahminleri mevcut `total_chars` hesabında kalır. Bu değişiklik token sayacının veya araç şeması rezervinin kesinliğini artırdığı iddiasını taşımaz. Sağlayıcı taşma öğrenmesi, özet süre sınırı, iptal, araştırma kanıtları ve özgün iz regresyonları hedefli olarak doğrulanmıştır. Canlı sağlayıcı, tarayıcı, native uygulama veya UI çalıştırılmamıştır.

## Doğrulama komutları

Çalışma ağacı kökünde `PYTHONPATH=src`; Python yolu `/Users/motogate/Desktop/all/01-Projeler/fusion-cli/.venv/bin/python`. `uv` ve tüm pytest paketi kullanılmadı.

- İlk hedefli regresyon grubu (210 başarılı; o sırada yeni dosyada 8 test): `python -m pytest -q tests/test_protected_context_budget.py tests/test_context_budget.py tests/test_turn_compaction.py tests/test_context_invariants.py tests/test_d4_compaction_errors.py tests/test_manual_compact.py tests/test_context_data_regressions.py tests/test_active_context_projection.py tests/test_agent_loop.py`. Bir mevcut Pydantic `ReadOnly` uyarısı vardı.
- Son ek testler dahil doğrulama (70 başarılı, 10,20 saniye): `python -m pytest -o addopts='' -q tests/test_protected_context_budget.py tests/test_ajan_dongusu_d2.py tests/test_d11_tur_bitis.py tests/test_original_trace_runtime.py`.
- `python -m ruff check src/fusion_cli/engines/agent/context_budget.py src/fusion_cli/engines/agent/loop.py tests/test_protected_context_budget.py`: başarılı.
- `MYPYPATH=src python -m mypy --follow-imports=silent src/fusion_cli/engines/agent/context_budget.py src/fusion_cli/engines/agent/loop.py`: iki kaynak dosyada hata yok.

Bağımsız inceleme sonrası küçük pencere kontrolü önce 8K/16K için beklenen `ConfigError` ile kırmızı izlendi; model boyuna göre rezerv hesabı düzeltildikten sonra hedefli grup yeniden çalıştırıldı.

Son rezerv düzeltmesinden sonra: `python -m pytest -o addopts='' -q tests/test_protected_context_budget.py tests/test_context_budget.py tests/test_turn_compaction.py tests/test_ajan_dongusu_d2.py tests/test_d11_tur_bitis.py tests/test_original_trace_runtime.py` — **107 başarılı, 14,45 saniye**. Aynı Ruff ve mypy komutları tekrar başarılı; `git diff --check` temiz.
