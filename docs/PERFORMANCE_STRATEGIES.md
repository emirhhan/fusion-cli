# Fusion-CLI — LLM Performans Stratejileri (Lite Rehber)

Ücretsiz / yerel LLM'lerle yüksek performanslı sonuç almak için kullanılan tekniklerin
kısa, uygulanabilir özeti. Her başlıkta: **ne işe yarar**, **ne zaman kullan**, **Fusion-CLI'da nasıl açılır**.

> Bağlam: Fusion-CLI zaten bir "performans katmanı"dır — paralel aday + hakem + sentez +
> öz-öğrenen bellek. Aşağıdaki teknikler bu katmanın *içini* besler: daha iyi prompt, daha
> akıllı bağlam, daha ucuz token.

---

## 1. Prompt Caching (İstem Önbelleği)

**Ne işe yarar:** Sistem promptu, araç tanımları ve uzun geçmiş gibi *değişmeyen* kısımlar
sağlayıcıda önbelleğe alınır; tekrar gönderilmez → daha düşük token maliyeti ve gecikme.

**Ne zaman:** Uzun sistem promptu (Fusion agent modu), sabit araçşemaları, uzun çok-turlu
sohbet geçmişi olan oturumlarda.

**Fusion-CLI'da:** LiteLLM `acompletion` çağrılarında `caching=True` ile açılabilir. Şu an
`providers/litellm_provider.py` bunu set etmiyor; istersen `cache_control` meta'sı
ekleyerek etkinleştirebilirsin (NIM/OpenRouter destekliyorsa). Geçmiş sıkıştırma
(`engines/agent/compaction.py`) zaten token tasarrufu sağlar — caching ile birleştir.

---

## 2. Few-Shot / Örnek Tabanlı İstem

**Ne işe yarar:** Modele 2-5 iyi örnek (girdi→çıktı) verirsin; küçük modeller "formatı" ve
"beklentiyi" örnekten kaparak daha tutarlı sonuç verir.

**Ne zaman:** Yapılandırılmış çıktı (JSON, tablo), kod üretimi, sabit bir stil gerektiğinde.

**Fusion-CLI'da:** Hakem zaten katı JSON ister (`engines/fusion/prompts/judge.txt`). Kendi görevlerin
için agent sistem promptuna (`engines/agent/prompts/system.md`) birkaç örnek enjekte edebilirsin. Daha
sistematik yol: **ders belleği** (`memory/lessons.py + engines/agent/learning.py`) — agent her görevden ders çıkarır ve
gelecekte benzer görevlerde sistem promptuna enjekte edilir (`runtime.lessons: true`).

---

## 3. RAG (Retrieval-Augmented Generation)

**Ne işe yarar:** Modelin bilmediği / güncel / proje-özel bilgiyi *önce* getirip bağlama
koyarsın; halüsinasyonu azalır, doğruluk artar.

**Ne zaman:** Kendi kod tabanın, dokümanların, changelog'lar, iç wiki sorulduğunda.

**Fusion-CLI'da:** Yerleşik.
- **Kod RAG:** `/reindex` ile çalışma dizini ChromaDB'ye vektörlenir; agent
  `search_codebase` ile anlamsal arar (`memory/code_index.py`).
- **Ders RAG:** `lessons.py` ChromaDB'de embedding'lenir; benzer görevlerde çekilir.
- **Embedding sağlayıcı:** `config.yaml → embedding.provider` → `local` (offline ONNX) veya
  `nim` (çok-dilli, Türkçe daha iyi).

---

## 4. Chain-of-Thought (CoT) / Adım Adım Düşünme

**Ne işe yarar:** Karmaşık görevlerde modeli "önce düşün, sonra cevap ver"e zorlarsın;
mantık hataları azalır. Reasoning modelleri (Nemotron 3 Nano) bunu doğal yapar.

**Ne zaman:** Matematik, çok adımlı kod, hata teşhisi, mimari karar.

**Fusion-CLI'da:**
- `task_type: reasoning` → Nemotron Nano gibi reasoning modeline yönlenir (`task_model_map`).
- Zor kararlarda agent **council** çağırır (çoklu model paralel, sentez) — `cli.py` içinde.
- Agent **self_review** (`runtime.self_review: true`) her turu kritik modele denetletir,
  sorun bulursa TEK düzeltici tur verir.

> Dikkat: CoT token maliyetini artırır. Hakem modeli *instruct* (düşünme yükü olmayan) bir
> model olmalı — aksi halde JSON kesilir (`runtime.judge_max_tokens` ile sınırlı).

---

## 5. Fine-Tuning (İnce Ayar)

**Ne işe yarar:** Sabit bir görev/ton için kendi modelini eğitirsin; inference'da prompt
kısar, hız/maliyet düşer, tutarlılık artar.

**Ne zaman:** Çok yüksek hacimli, sabit biçimli, domain-özel görevlerde (ör. hep aynı tip
kod üretimi). Ücretsiz API'lerde genelde *yok*; yerel/Ollama'da mümkün.

**Fusion-CLI'da:** Doğrudan fine-tune aracı yok (ücretsiz sağlayıcılar desteklemiyor). Ancak
**öz-öğrenen bellek** (feedback + dersler) "soft fine-tuning" gibi davranır: `/good` `/bad`
feedback'i ve çıkarılan dersler zamanla model önceliğini ve prompt enjeksiyonunu iyileştirir
— eğitimsiz ama *adaptif*. Yerel bir fine-tune modelin varsa `config.yaml`'a
`ollama/<model>` olarak ekleyip aday yapabilirsin (bkz. `config.yaml` altındaki
`local_llm_candidates` örnek bloğu).

---

## 6. Hız & Dayanıklılık (Fusion'a özel)

Bunlar "model stratejisi" değil ama ücretsiz LLM'lerde performansın bel kemiği:

- **Hedged istek:** Birincil + fallback modeller *aynı anda* çağrılır, ilk dönen kazanır
  (`router/litellm_client.py:acomplete`). Tek-nokta-arıza yok.
- **Straggler kesme:** `candidate_hard_cap_s` (vars. 25s) ve `straggler_grace_s` (6s) ile
  yavaş/soğuk model turu kilitlemez.
- **Hakem deadline:** `judge_timeout_s` (12s) aşılınca hakem atlanır, sezgisel kazanana düşülür.
- **Warm-up:** REPL açılırken agent modeli arka planda ısıtılır (NIM soğuk başlangıcı gizlenir).
- **Bağlam sıkıştırma:** Geçmiş eşiği aşınca eski turlar özetlenir (uzun oturum koruması).

---

## Özet Tablo

| Teknik | Etkisi | Fusion-CLI durumu |
|--------|--------|-------------------|
| Prompt caching | Maliyet ↓, gecikme ↓ | Manuel açılabilir (`_one_call`) |
| Few-shot | Tutarlılık ↑ | Ders belleği ile soft |
| RAG | Doğruluk ↑, halüsinasyon ↓ | Yerleşik (kod + ders) |
| CoT | Mantık ↑ | Reasoning modu + council |
| Fine-tune | Hız ↑, tutarlılık ↑ | Soft (feedback+bellek); yerel model eklenebilir |
| Hedged/kesme | Dayanıklılık ↑ | Yerleşik |
