# Uzun Görev Paritesi Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fusion’ın uzun, çok dosyalı ve doğrulama gerektiren Gate Holding/MotoGate işlerinde gerçek çıktıyı kabul testleriyle kanıtlayarak Claude Code düzeyine yaklaşmasını sağlamak.

**Architecture:** Görevler önce araştırma ve planlama, sonra araçla uygulama, ardından bağımsız kabul ve adversarial inceleme döngüsünden geçecek. Her koşu model çağrısı, araç hatası, yeniden deneme, bağlam ve kabul sonucunu ayrı kaydedecek.

**Tech Stack:** Python agent loop, typed tools, Playwright acceptance, Next.js/TypeScript fixture, pytest, Ruff, mypy.

**Spec:** `FUSION_MASTER_PROJE_DOKUMANI.md`, Faz 12–14 ve `evals/suite/production.yaml`.

## Global Constraints

- Kişisel proje `.env` dosyaları okunmayacak veya kopyalanmayacak.
- Gerçek kullanıcı projeleri doğrudan değiştirilmeden önce izole kopyada koşulacak.
- Uzun görev başarı sayılması için model beyanı değil davranışsal kabul ölçütü geçecek.
- Her faz sonunda `ruff check`, `mypy` ve `pytest` temiz olacak.

## Review Focus

- Modelin mutlak dosya yolu ile proje dışına yazmayı denemesi: araç şeması göreli yol kuralını açıkça vermeli.
- Uzun üretimde bağlamın büyümesi: transkript ve sıkıştırma gerçek token/süre kanıtı üretmeli.
- Tarayıcı yerel adresi güvenlik kapısına takıldığında: model doğru yerel acceptance komutuna dönmeli.
- “Bitti” beyanı ile gerçek çıktı ayrışması: bağımsız kabul koşulu başarısızsa tur başarısız sayılmalı.
- Gate Holding/MotoGate gibi çok modüllü projede test/build/çalışan sayfa birlikte doğrulanmalı.

### Task 1: Araç yönlendirmesi ve uzun görev telemetrisi

**Files:** `src/fusion_cli/tools/builtin.py`, `evals/transcript.py`, ilgili testler.

- [x] Mutlak dosya yolu hatasını araç açıklamasında önle.
- [x] Model ve araç sürelerini transkriptte ayır.
- [ ] Uzun görevde bağlam bütçesi ve kabul döngüsü metriklerini rapora ekle.

### Task 2: Gerçek proje acceptance fixture’ı

**Files:** `evals/suite/gate_holding.yaml`, `evals/criteria/` ve testler.

- [ ] Gate Holding’in `.env` içermeyen izole fixture’ını oluştur.
- [ ] TypeScript, Vitest ve Next build sonuçlarını tek kabul komutunda doğrula.
- [ ] Dashboard görsel/etkileşim ve veri kaynağı sözleşmelerini davranışsal kontrol et.

### Task 3: Uzun görev orchestrator döngüsü

**Files:** `src/fusion_cli/engines/agent/loop.py`, `core/budget.py`, compaction ve review modülleri.

- [ ] Plan adımlarını tek geçmişte taşı ve her adım için kanıt üret.
- [ ] Kabul başarısızlığını bağımsız düzeltme turuna bağla.
- [ ] İlerleme yoksa döngüyü kes; ilerleme varsa uzun görev bütçesini tüketmeden sürdür.

### Task 4: Üç tekrar ve adversarial rapor

- [ ] Gate Holding görevini üç ayrı koşuda çalıştır.
- [ ] MotoGate çoklu entegrasyon görevini üç ayrı koşuda çalıştır.
- [ ] Her başarısızlıkta kök nedeni düzelt ve yeniden koş.
- [ ] Claude oturum çıktısı bulunursa aynı görevlerle karşılaştır; bulunamazsa karşılaştırmayı kanıtsız eşdeğerlik olarak sunma.
