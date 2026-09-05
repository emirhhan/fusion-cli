# Genel Agent Güvenilirliği Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax for tracking.

**Goal:** Genel araç aktarımı, doğrulama, kurtarma ve teslim boşluklarını gerçek kanıtla kapatmak.

**Architecture:** Mevcut core sözleşmeleri genişletilir; MCP/provider adaptörleri veriyi korur, plan motoru tipli kanıtı tüketir. Güvenlik ve onay tek mevcut yolda kalır.

**Tech Stack:** Python 3.11+, dataclasses, MCP Python SDK, Playwright, pytest, Tauri/macOS.

**Spec:** `docs/superpowers/specs/2026-09-05-genel-agent-guvenilirligi-design.md`

## Global Constraints

- Mevcut dal ve kullanıcı değişiklikleri korunur; yeni branch açılmaz.
- Depo `.env` içeriği okunmaz, çıktıya veya rapora yazılmaz.
- Kod metinleri Türkçe; tanımlayıcılar İngilizce; mevcut katman yönü korunur.
- RED görülmeden üretim kodu yazılmaz. Her faz ruff format/check, mypy, pytest ve deadlock kapısı ardından commit edilir.
- Ücretsiz ve anahtarsız çalışma yolu korunur; yeni servis aboneliği gerekmez.
- Kod incelemesini ana ajan ayrı reviewer'a yaptırır; implementer alt-ajan açmaz.
- Bağımsız özellikler aynı anda değiştirilmez. Controller sonraki fazın araştırma ve ölçüm hazırlığını yapabilir.

### Task 1: MCP ve sağlayıcılar arasında içerik taşıma

**Files:** `core/tools.py`, gerekirse yeni `core/tool_content.py`; `mcp_bridge/client.py`, yeni `mcp_bridge/content.py`; `engines/agent/loop.py`, gerekirse yeni `engines/agent/tool_feedback.py`; `providers/web_session.py`, `providers/web_browser.py`, `providers/web_transport.py`; ilgili mevcut provider mesaj dönüştürücüleri; `tests/test_mcp.py`, yeni `tests/test_tool_content.py`, `tests/test_web_session.py`.

**Interfaces:** Mevcut `ToolResult(output, ok)` kurucuları çalışmaya devam eder. Sonuca tipli içerik blokları ve yapılandırılmış JSON eklenir. MCP call artık anlamlı `ToolResult` döndürür; iç çağıranlar ve testler güncellenir. `Message.images` mevcut multimodal köprü olarak kullanılır; provider protokolü değiştirilmez.

- [ ] RED: gerçek MCP SDK sonuçlarında text + image + structuredContent + resource_link korunmalı; yalnız image cevabı boş başarılı metne dönüşmemeli; `isError` korunmalı.

```python
result = await client.call("fixture", "inspect", {})
assert result.ok
assert result.images == ("data:image/png;base64,aGVsbG8=",)
assert '"score": 5' in result.output
```

Bu örnekte `images` ToolResult üzerinde property olabilir; kaynak içerik için tek temsil kullanılır. Büyük içerik mevcut sınırlarla açıkça sınırlandırılır, sessiz eksiltme yapılmaz. Metin dışı veri base64 olarak model metnine dökülmez.

- [ ] RED: araç listesi ikinci sayfadaki aracı da kaydetmeli; yinelenen cursor sonsuz döngü olmamalı.
- [ ] RED: agent döngüsündeki gerçek registry aracından gelen görsel sonraki CompletionRequest'e ulaşmalı. Structured/resource bilgisi modelin gördüğü metinde görünmeli.
- [ ] RED: web adaptörü görseli sessizce atamaz. Native olmayan aktarımda açıklama veya açık desteklenmiyor bilgisi korunmalı; görüntü gerçekten incelenmeden incelendi iddiası doğmamalı.
- [ ] GREEN: core içerik ve MCP normalleştiricisini uygula; liste pagination ve cleanup hatalarını düzelt; engine feedback ve provider dönüşümünü bağla. Görsel fallback için mevcut `image_view`/vision yapılandırmasını kullan; gerekirse controller'a gerekli bağımlılık bilgisini bildir.
- [ ] Test: `.venv/bin/python -m pytest -q tests/test_mcp.py tests/test_tool_content.py tests/test_web_session.py tests/test_web_conversation.py tests/test_attachment_images.py` ve değişen tüketici testleri.
- [ ] `make check` çalıştır; yalnız sahip olunan dosyaları commit et. Sonuçları task raporuna yaz. Commit: `fix(arac): MCP icerigini agent ve saglayicilara kayipsiz tasi`.

### Task 2: Başarı kriterlerine bağlı doğrulama

**Files:** `core/execution_plan.py`, `core/verification.py`, yeni `core/evidence.py`, `engines/agent/plan_parser.py`, `engines/agent/prompts/execution_plan.md`, `engines/agent/step_verification.py`, `engines/agent/verification.py`; ilgili testler.

**Interfaces:** PlanStep'e geriye uyumlu tipli kontrol alanları ekle. Kontrol sonucu passed/failed/unverified, criterion kimliği ve artifact/komut kanıtını taşır. Mevcut VerificationResult kullanıcıya görünen bulguları korur.

- [ ] RED: boş dosya hareket kriterini doğrulanmış sayamaz; yalnız genel çağrı sayısı git etkisini kanıtlayamaz; tanımlı ama çalıştırılmamış test uyarıyı kaldıramaz.
- [ ] RED: içerik kontrolü gerçek dosyayı okur; komut kontrolü gerçek çıkış/çıktı taşır; bilinmeyen veya eksik kontrol unverified kalır; engellenmiş komut çalıştırılmaz.

```python
result = await verify_step(step, outcome, deps)
assert result.unverified
assert not any("hareket doğrulandı" in item for item in result.evidence)
```

- [ ] GREEN: mevcut kapıları tipli kanıta bağla. Modelin ürettiği keyfi komutu doğrudan doğrulayıcıdan çalıştırma; mevcut araç onay/shell güvenlik yolunu kullan. Otomatik keşif yalnız projede var olan kontrolü çalıştırır. Gerçek komut çalıştırılmış kayıt final sonucuna taşınır.
- [ ] RED/GREEN: yeni boş projede final koşullarını erken adımlara zorlayıp kilitlenme yaratma; plan kriterlerine ilişkin unverified durumu açık kalır.
- [ ] İlgili testler ve `make check`; reviewer; commit.

### Task 3: Final onarımı, kanıtlı checkpoint ve araç sınırları

**Files:** `engines/agent/plan_runner.py` ve sorumluluklarına göre yeni yardımcılar; `engines/agent/recovery.py`; `core/checkpoint.py`; `memory/checkpoint_store.py`; `tests/test_plan_runner.py`, `tests/test_plan_resume.py`, `tests/test_checkpoint_store.py`.

**Interfaces:** Task 2 kontrol kanıtları checkpoint'e serileştirilir. Adım aileleri ToolFamily üzerinden gerçek registry adlarına çevrilir. Final onarım mevcut recovery bütçesini tüketir; yeni sabit hak uydurulmaz.

- [ ] RED: son adım önceki dosyayı bozunca final düşmeli, ilişkili güvenli adım yeniden açılıp onarılmalı, final yeniden çalışmalı.
- [ ] RED: onarım hakkı bittiğinde checkpoint PAUSED kalmalı; tamamlanan bağımsız adım tekrar edilmemeli.
- [ ] RED: OBSERVE_FIRST gözlem turunda mutating araçlar kapalı olmalı; NEVER yan etki otomatik tekrarlanmamalı.
- [ ] RED: checkpoint round-trip kontrol kanıtlarını korumalı; değişen artifact eski kanıtı geçersiz kılmalı.
- [ ] GREEN: plan runner'ı küçük yardımcılarla düzenle; yalnız gerçek dependency kanıtını geçir; final ve planning sayaçlarını raporla. Mevcut oturum devamı bozulmaz.
- [ ] İlgili testler ve `make check`; reviewer; commit.

### Task 4: Genel kabul ölçümleri ve bilgi erişimi

**Files:** `evals/` mevcut suite/runner, `tests/test_professional_execution_eval.py`; gerekirse `engines/agent/skill_recall.py`, `engine_tools.py`; rapor `docs/superpowers/reports/2026-09-05-genel-agent-kabul.md`.

- [ ] RED/GREEN: gerçek dosya + shell, yerel MCP structured/image, web kullanıcı akışı ve Godot import/runtime hata örnekleri ortak kanıt sistemiyle ölçülür.
- [ ] Uygun skill'in seçildiğini, tamamının okunabilirliğini ve gerekli araçların görünür olduğunu gerçek tüketici üzerinden sınayan test ekle; yalnız kaynak metni arayan test yazma.
- [ ] Mevcut canlı koşu yöntemini/kimliksiz yapılandırmayı keşfet. Temiz dizinlerde düşük maliyetli sabit görevleri çalıştır; provider/call/acceptance/artifact/human-repair metriklerini kaydet.
- [ ] Çıktı başarısızsa hangi katmanın koptuğunu belirt, kanıtlı genel kusuru RED/GREEN ile düzeltip yalnız etkili ölçümü yinele.
- [ ] `make check`; reviewer; commit. Başarılı tek örneği bütün alanlar için garanti olarak yazma.

### Task 5: Masaüstü paket ve kurulu runtime kabulü

**Files:** Mevcut `desktop_build/`, `app/package.json`, build artifact'leri; teslim raporu.

- [ ] `app` kalite kapısını çalıştır; yeni hata varsa ilgili sorumlulukta düzelt.
- [ ] Mevcut runtime build/smoke ve macOS bundle/smoke komutlarını kullan; bağımlılıkları gereksiz yükseltme.
- [ ] Güncel paketi güvenli geçici hedefle kur; önceki çalışan uygulamayı geri dönüş için koru. Kaynak/paket/kurulu manifest ve ilgili kaynak hash'lerini karşılaştır.
- [ ] Kurulu protokolde basit araç/MCP kabulü ve runtime kimliğini doğrula. UI sonucu ve doğrulanamamış davranış mesajlarının kullanıcıya ulaştığını sınayarak raporla.
- [ ] Bütün değişikliklerin son bağımsız incelemesi; son ölçüm raporu, kalan sınırlamalar ve teslim bilgisi.
