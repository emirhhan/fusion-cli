# Faz 3 — Onay/Soru Modalları Implementation Plan

> **For agentic workers:** Bu plan inline (aynı oturumda, TDD ile) uygulanır.
> Adımlar checkbox (`- [ ]`) ile izlenir.

**Goal:** Tam-ekran kabukta agent turunun `confirm`/`ask` çağrılarını gerçek modal diyalogla karşılamak (Faz 2'deki etkileşimsiz reddetme yerine).

**Architecture:** `FusionScreen` root'u `FloatContainer` olur; aktif modal bir `Float` + `ConditionalContainer` ile gösterilir. Yeni `ScreenPrompter` (`Prompter`+`UserAsker`) motor çağrılarını `screen.ask_confirm`/`screen.ask_text`'e köprüler; bunlar `asyncio.Future` ile cevabı bekler. Motor katmanına dokunulmaz.

**Tech Stack:** Python 3.11, prompt_toolkit 3.0.52, pytest, ruff, mypy.

## Global Constraints

- Kod içi Türkçe (docstring, yorum, kullanıcıya görünen metin). Tanımlayıcılar İngilizce + PEP 8.
- Motor/çekirdek katmanına DOKUNULMAZ. Mevcut REPL (bayraksız yol) DEĞİŞMEZ.
- Kaydırma/tekerlek reçetesi (spike4: mouse_support=False + ?1h + TextArea + imleç kaydırma) BOZULMAZ.
- Kalite kapısı her task sonunda: `.venv/bin/ruff check` + `.venv/bin/mypy` + `.venv/bin/python -m pytest -q`.
- Commit: conventional, Türkçe açıklama, faz/adım no YOK, author/co-author YOK. `main` üzerinde.

---

### Task 1: `FusionScreen` modal altyapısı

Root'u `FloatContainer`'a çevir; aktif modalı `_modal` durumunda tut; `ask_confirm`/`ask_text` async metotlarını ekle. Modal açıkken odak modala, kapanınca girişe döner.

**Files:** Modify `src/fusion_cli/cli/repl/screen.py`; Test `tests/test_screen_modal.py`

**Interfaces (Produces):**
- `async FusionScreen.ask_confirm(preview: str, danger: str | None = None) -> bool`
- `async FusionScreen.ask_text(question: str) -> str`
- İç: `_modal` durumu (`None` | ("confirm", Future, preview, danger) | ("text", Future, question, TextArea)).

**Yaklaşım:**
- `root_float = FloatContainer(content=<mevcut HSplit>, floats=[Float(ConditionalContainer(_modal_view, filter=Condition(lambda: self._modal is not None)))])`.
- `_modal_view`: `_modal` tipine göre confirm (Label preview + "Onayla (e) / Reddet (h)") ya da text (Label question + TextArea) çizen dinamik container. En basit: iki ayrı Frame'i ConditionalContainer'larla topla.
- `ask_confirm`: `fut = get_event_loop().create_future()`; `_modal = ("confirm", fut, preview, danger)`; odak modala; `invalidate`; `res = await fut`; `_modal = None`; odağı girişe al; `invalidate`; return res.
- `ask_text`: benzer; bir TextArea kullan, `accept_handler` fut'u metinle çözer.
- Key bindings (yeni, filtreli — yalnız confirm modal aktifken): `e`/`y` → fut True; `h`/`n`/`escape` → fut False. Filter: `Condition(lambda: self._modal is not None and self._modal[0] == "confirm")`.

- [ ] **1. Yaz: başarısız test** — `ask_confirm` bir Future kurup modalı açıyor; Future çözülünce sonucu döndürüyor. Test: `ask_confirm`'i task olarak başlat, `_modal` set olduğunu doğrula, confirm tuş-çözücüsünü çağır (Future'ı True yap), `await` sonucu True.
- [ ] **2. RED çalıştır** — `AttributeError: ask_confirm`.
- [ ] **3. Uygula** — yukarıdaki yaklaşım.
- [ ] **4. GREEN + kalite kapısı + commit** — `feat(repl): tam-ekran kabukta onay/soru modal altyapısı`

---

### Task 2: `ScreenPrompter`

Motor `Prompter`+`UserAsker` çağrılarını modala köprüler.

**Files:** Modify `src/fusion_cli/cli/repl/screen_turn.py`; Test `tests/test_screen_turn.py`

**Interfaces (Produces):**
- `class ScreenPrompter` — `async confirm(request: ApprovalRequest) -> bool` (önizleme kurar → `screen.ask_confirm`), `async ask(question: str) -> str` (→ `screen.ask_text`).
- Yardımcı: `_preview(request) -> str` — araç adı + argümanlar (mevcut prompter'ın `_summary` deseniyle tutarlı, düz metin).

- [ ] **1. Yaz: başarısız test** — sahte bir screen (ask_confirm/ask_text kaydeden) ile ScreenPrompter.confirm/ask'in doğru metni geçirdiğini ve sonucu döndürdüğünü doğrula.
- [ ] **2. RED** — import hatası.
- [ ] **3. Uygula.**
- [ ] **4. GREEN + kalite kapısı + commit** — `feat(repl): motor onay/soru çağrılarını modala bağlayan ScreenPrompter`

---

### Task 3: `run_turn` bağlama + elle doğrulama

`NonInteractivePrompter` yerine `ScreenPrompter`; agent turunda `interactive=True`.

**Files:** Modify `src/fusion_cli/cli/repl/screen_turn.py`; Test `tests/test_screen_turn.py`

- [ ] **1. Test güncelle** — agent dalında prompter_factory'nin `ScreenPrompter` döndürdüğü, `interactive=True` geçtiği doğrulanır.
- [ ] **2. Uygula** — `run_turn` agent dalını güncelle (prompter_factory=lambda _drain: ScreenPrompter(screen), interactive=True). `NonInteractivePrompter`'ı kaldır.
- [ ] **3. GREEN + tam süit + kalite kapısı.**
- [ ] **4. Elle görsel doğrulama (insan):** `FUSION_FULLSCREEN=1 fusion` → agent modunda onay isteyen bir araç tetikle; modal açılır, `e`/`h` çalışır; soru sorulunca metin girişi çalışır. Sorun olursa Task 1/2'ye dönülür.
- [ ] **5. Commit** — `feat(repl): agent turunu gerçek onay/soru modalına bağla`

---

## Self-Review Notları
- Kapsam: modal altyapı (T1), köprü (T2), bağlama+doğrulama (T3). Faz 3 tasarımı karşılanıyor.
- Risk: modal odak/Future ve tuş bağlamaları gerçek terminalde elle doğrulanır (T3.4).
- Kapsam dışı: zengin/renkli diff önizlemesi (düz metin; renk Faz 4 backlog).
