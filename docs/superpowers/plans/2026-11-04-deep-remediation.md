# Fusion derin denetim düzeltme planı

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development veya superpowers:executing-plans. Adımlar tests-first uygulanır.

**Goal:** A01–D04 kök nedenlerini doğrulayarak düzeltmek ve yapılmamış kabulü açık tutmak.
**Architecture:** Mevcut hedef/izin, teslim kanıtı, bağlam ve eval sözleşmeleri genişletilir.
**Tech Stack:** Python asyncio/pytest, Chrome JavaScript, React/TypeScript.
**Spec:** docs/remediation/spec.txt; önceki raporun screenshot görev yönlendirmesi bulgusu da kapsamda.

## Global Constraints
- RULES.md uygulanır; yalnız izole worktree içinde yazılır.
- Gerçek model/ağ, kullanıcı sırları, OS/hesap izin değişikliği ve kurulum değişikliği yok.
- Her davranış için red/green; gerekli uzman review; make check ve UI kontrolleri.
- Baseline 2b2c8fe4 önceki değişikliklerdir; yeni düzeltme sayılmaz.
- Gerçek platform/notarization/canlı kabul açık gap kalır. Yeni parent adayları ayrı ledger.

## Review Focus
- Seçili cihaz kopuşunda yanlış hesaba sıfır komut (A01).
- Feed sınırı/yeni panel/yüzey yarışı pending soruyu kaybettirmez (A02/A03).
- Readiness/install iptalinde süreç ağacı sonlandırılır ve wait edilir (C06).
- Son mutasyon ve ilgili kriter doğrulaması başarıyı belirler (C01–C03).
- Uzun ara düzeltmenin sonu ve çok kaynaklı kanıt korunur (B01–B03).

### Task 1: Hedef ve onay sahipliği
Files: appserver/chrome_devices.py, chrome_bridge.py, chrome-extension/panel.js, tools/preview_server.py; ilgili tests.
- [ ] A01–A03/C06 için bağımsız kök neden ve kırmızı davranış testleri.
- [ ] Seçim/pending snapshot/cevap kabulü/süreç cleanup düzeltmeleri.
- [ ] İlgili testler, kalite kontrolleri ve task review.

### Task 2: Tek güncel teslim kararı
Files: agent/turn_report.py, loop.py, browser_verify.py, completion_evidence.py, output_verify.py, teacher_flow.py; app delivery evidence/card ve tests.
- [ ] C01–C05+screenshot yönlendirme için kırmızı testler.
- [ ] Toparlanan hata, son mutasyon, ölçülmedi ve tür/güncellik doğrulamasını düzelt.
- [ ] İlgili testler ve Python/TypeScript/React incelemesi.

### Task 3: Model, bağlam, kaynak
Files: agent/masking.py, history.py, compaction.py; config/model_select.py; providers/factory.py; tools/web.py/builtin.py; ilgili tests.
- [ ] B01–B07 için ağsız red/green, model kimliğine ait metadata korunması.
- [ ] Kaynak ve uzun ara talimat koruması; provenance/gerçek tarih filtresi; uydurma tarih yok.
- [ ] Loop değişikliği controller ile koordine; ilgili testler ve task review.

### Task 4: İzin deneyimi
Files: chrome-extension/panel.js/core.js/panelView.js; agent approval/site approval; ui/chrome_site_labels.py ve tests.
- [ ] A04–A07 red/green: kapsam görünürlüğü/geri alma, reconnect, geç cevap/ret/zaman aşımı.
- [ ] Mevcut güvenlik katmanları korunarak düzelt; ilgili testler ve review.

### Task 5: Temsili ölçüm/yayın
Files: evals/suite/production.yaml, evals/agent_runner.py/tasks.py; release/known-gaps.json; docs/workflows ve tests.
- [ ] D01–D04 doğrulaması; sahte çıktıyı reddeden red/green; isimler ölçülen kapsamla eşleşir.
- [ ] Onay/intervention ölçümü ve canlı rapor model/config/paket kimliği sözleşmesi.
- [ ] Yapılmamış gerçek platform kabulleri açık; testler ve review.

### Task 6: Bütünleşik teslim
- [ ] make check, app check ve eklenti Node testleri; exact test/failure kaydı.
- [ ] code-reviewer/python-reviewer ve dokunulan TS/React uzman review; düzeltme sonrası tekrar doğrula.
- [ ] Ledger durumları, commitler, patch ve kurulum gerekliliklerini teslim et; kurulum yapma.
