# Geçmiş İçe Aktarma Uygulama Planı

> **Agentic worker'lar için:** ZORUNLU ALT BECERİ: Bu planı görev görev uygulamak
> için `superpowers:subagent-driven-development` (önerilen) ya da
> `superpowers:executing-plans` kullan. Adımlar takip için checkbox (`- [ ]`)
> sözdizimi kullanır.

**Hedef:** Fusion, Claude Code / Codex / Hermes oturum geçmişini listeleyip bir
oturumu devralabilsin ve diğer araçların bellek dosyalarını sistem promptuna alsın.

**Mimari:** Yeni `src/fusion_cli/history/` paketi arayüzden bağımsız çekirdeği
tutar: kaynak adapter'ları, kurulu araç tespiti ve künye üretimi. CLI yüzeyleri
(dinamik `/resume<kaynak>` komutları, açılış listesi) ve ajan aracı
(`read_session`) bu çekirdeği çağırır. Planlanan masaüstü uygulaması aynı
çekirdeği kullanacağı için hiçbir davranış CLI katmanına gömülmez.

**Teknoloji:** Python 3, stdlib `json` + `sqlite3`, mevcut `ui/picker.py`,
mevcut `CapabilityRegistry(home, root)` deseni. Yeni bağımlılık yok.

## Global Kısıtlar

- Docstring, yorum, log ve kullanıcıya görünen tüm metinler **Türkçe**; tanımlayıcılar
  **İngilizce** ve PEP 8 uyumlu (RULES.md "Dil").
- Kullanıcıya görünen metinler modüle dağıtılmaz, `ui/messages.py`'de toplanır
  (RULES.md "Dil", 3. madde).
- Modül seviyesinde iş yapılmaz; import anında ağ/dosya/DB erişimi olmaz
  (RULES.md "Dil Kuralları").
- Dosya 800 satırı geçmez, fonksiyon 50 satırı geçmez.
- Sır **maskelenmez**; yalnızca sayılır ve kullanıcıya bildirilir (spec "Sırlar").
- Ev dizini her zaman parametre olarak geçilir; hiçbir modül `Path.home()`'u
  kendi içinde çağırmaz — testler gerçek `~` dizinine bağımlı olamaz.
- Tek bir bozuk dosya tüm keşfi düşüremez.
- Her görev sonunda kalite kapısı: `ruff check` + `mypy` + `pytest` üçü de temiz
  olmadan commit atılmaz (CLAUDE.md "Geliştirme Akışı").
- Commit mesajları conventional format, açıklama Türkçe, faz/adım numarası yok
  (CLAUDE.md "Commit").

## Dosya Yapısı

| Dosya | Sorumluluk |
|---|---|
| `src/fusion_cli/history/__init__.py` | Paket dışına açılan yüzey: `available_sources`, `build_digest` |
| `src/fusion_cli/history/models.py` | `SessionRef`, `Turn`, `HistorySource` protokolü |
| `src/fusion_cli/history/claude_source.py` | Claude Code JSONL okuyucusu |
| `src/fusion_cli/history/codex_source.py` | Codex SQLite + `session_index.jsonl` okuyucusu |
| `src/fusion_cli/history/hermes_source.py` | Hermes SQLite okuyucusu |
| `src/fusion_cli/history/registry.py` | Kurulu kaynak tespiti ve ada göre çözme |
| `src/fusion_cli/history/digest.py` | Deterministik künye + sır sayımı |
| `src/fusion_cli/history/memory_files.py` | Diğer araçların bellek dosyalarını okuma |
| `tests/test_history_models.py` … `tests/test_history_digest.py` | Görev başına test |

Değiştirilecekler: `cli/repl/commands.py` (dinamik komut), `ui/messages.py`
(metinler), `engines/agent/engine_tools.py` (`read_session` aracı),
`engines/agent/project_instructions.py` (bellek dosyaları), `cli/repl/loop.py`
(açılış listesi).

---

### Task 1: Oturum modeli ve kaynak protokolü

**Files:**
- Create: `src/fusion_cli/history/__init__.py`
- Create: `src/fusion_cli/history/models.py`
- Test: `tests/test_history_models.py`

**Interfaces:**
- Consumes: yok (ilk görev).
- Produces: `SessionRef(source, session_id, title, updated_at, turn_count)`,
  `Turn(role, text, timestamp)`, `HistorySource` protokolü
  (`name: str`, `is_installed() -> bool`, `list(root: Path | None) -> tuple[SessionRef, ...]`,
  `read(session_id: str, cursor: int, limit: int) -> tuple[Turn, ...]`).

- [ ] **Step 1: Testi yaz**

`tests/test_history_models.py`:

```python
"""Geçmiş kaynaklarının ortak veri modeli."""

from __future__ import annotations

from fusion_cli.history.models import SessionRef, Turn


def test_oturum_kunyesi_alanlarini_tasir():
    ref = SessionRef(
        source="claude",
        session_id="abc",
        title="Başlık",
        updated_at=1_700_000_000.0,
        turn_count=12,
    )

    assert ref.source == "claude"
    assert ref.turn_count == 12


def test_oturum_kunyesi_degistirilemez():
    ref = SessionRef(
        source="claude", session_id="abc", title="B", updated_at=0.0, turn_count=1
    )

    try:
        ref.title = "yeni"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("SessionRef donmuş olmalı")


def test_tur_bos_metni_kabul_eder():
    turn = Turn(role="user", text="", timestamp=0.0)

    assert turn.role == "user"
    assert turn.text == ""
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_models.py`
Beklenen: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.history'`

- [ ] **Step 3: En küçük uygulamayı yaz**

`src/fusion_cli/history/__init__.py`:

```python
"""Başka araçların oturum geçmişini okuyan arayüzden bağımsız çekirdek.

CLI komutları, ajan aracı ve ileride masaüstü uygulaması aynı bu katmanı çağırır;
davranış hiçbir sunum yüzeyine gömülmez.
"""

from __future__ import annotations
```

`src/fusion_cli/history/models.py`:

```python
"""Geçmiş kaynaklarının ortak veri modeli ve protokolü.

Her araç (Claude Code, Codex, Hermes) geçmişini başka bir biçimde saklar. Bu modül
o biçimlerin TEK ortak görünümünü tanımlar: listelenebilir bir oturum künyesi ve
imleçle çekilebilen turlar. Yeni bir araç desteği eklemek, bu protokolü uygulayan
tek bir dosya yazmaktır.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SessionRef:
    """Listede gösterilen tek bir oturum. İçeriği DEĞİL, künyesi."""

    #: Kaynak etiketi: claude | codex | hermes
    source: str
    #: Kaynağın kendi kimliği. Aynı kaynak içinde benzersizdir.
    session_id: str
    #: Gösterilecek başlık. Çözüm sırası kaynağa göre değişir, boş olmaz.
    title: str
    #: Son değişiklik zamanı (unix saniye). Sıralama bunun üzerinden yapılır.
    updated_at: float
    #: Turdaki mesaj sayısı. Bilinmiyorsa 0.
    turn_count: int = 0


@dataclass(frozen=True, slots=True)
class Turn:
    """Bir oturumdaki tek bir mesaj."""

    #: user | assistant | system
    role: str
    text: str
    timestamp: float = 0.0


class HistorySource(Protocol):
    """Bir aracın geçmişini okuyabilen taraf.

    `list` ve `read` ASLA istisna fırlatmaz: bozuk kayıt atlanır, okunamayan kaynak
    boş döner. Tek bir bozuk dosya tüm keşfi düşürmemelidir.
    """

    #: Komut adında kullanılan kısa ad: /resume<name>
    name: str

    def is_installed(self) -> bool:
        """Bu aracın izi makinede var mı? Yalnızca varlık kontrolü, dosya açılmaz."""
        ...

    def list(self, root: Path | None = None) -> tuple[SessionRef, ...]:
        """Oturumları yeniden eskiye sıralı döndür. `root` verilirse o projeye ait
        olanlar önce gelir; kaynak proje bilgisi tutmuyorsa `root` yok sayılır."""
        ...

    def read(self, session_id: str, cursor: int = 0, limit: int = 50) -> tuple[Turn, ...]:
        """`cursor`'dan başlayarak en fazla `limit` tur döndür."""
        ...
```

- [ ] **Step 4: Testin geçtiğini gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_models.py`
Beklenen: 3 passed

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src/fusion_cli/history tests/test_history_models.py
.venv/bin/ruff format src/fusion_cli/history tests/test_history_models.py
.venv/bin/mypy src
git add src/fusion_cli/history tests/test_history_models.py
git commit -m "feat(history): oturum modeli ve kaynak protokolünü tanımla"
```

---

### Task 2: Claude Code okuyucusu

**Files:**
- Create: `src/fusion_cli/history/claude_source.py`
- Test: `tests/test_history_claude.py`

**Interfaces:**
- Consumes: `SessionRef`, `Turn`, `HistorySource` (Task 1).
- Produces: `ClaudeSource(home: Path)` — `name = "claude"`.
  Ayrıca `slug_for(root: Path) -> str` (dizin adı eşlemesi) dışa açılır; Task 10
  bellek dosyası yolunu bulmak için bunu kullanır.

Gerçek biçim (ölçüldü): `~/.claude/projects/<slug>/<oturum>.jsonl`, satır başına
bir JSON kaydı. İlgili tipler: `{"type":"user","message":{"role","content"},…}`,
`{"type":"assistant",…}`, `{"type":"ai-title","aiTitle":…}`. `content` alanı **ya
düz metin ya da parça listesi** olabilir. Üst seviyede `timestamp`, `cwd`,
`isMeta`, `isSidechain` alanları bulunur.

- [ ] **Step 1: Testi yaz**

`tests/test_history_claude.py`:

```python
"""Claude Code JSONL okuyucusu."""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.history.claude_source import ClaudeSource, slug_for


def _oturum_yaz(home: Path, slug: str, session_id: str, kayitlar: list[dict]) -> Path:
    hedef = home / ".claude" / "projects" / slug
    hedef.mkdir(parents=True, exist_ok=True)
    yol = hedef / f"{session_id}.jsonl"
    yol.write_text("\n".join(json.dumps(k) for k in kayitlar), encoding="utf-8")
    return yol


def test_slug_yol_ayraclarini_tireye_cevirir():
    assert slug_for(Path("/Users/x/Desktop/proje")) == "-Users-x-Desktop-proje"


def test_iz_yoksa_kurulu_degil(tmp_path):
    assert ClaudeSource(tmp_path).is_installed() is False


def test_iz_varsa_kurulu(tmp_path):
    (tmp_path / ".claude" / "projects").mkdir(parents=True)

    assert ClaudeSource(tmp_path).is_installed() is True


def test_ai_title_varsa_baslik_odur(tmp_path):
    _oturum_yaz(
        tmp_path,
        "-p",
        "s1",
        [
            {"type": "user", "message": {"role": "user", "content": "ilk soru"}},
            {"type": "ai-title", "aiTitle": "Gerçek Başlık", "sessionId": "s1"},
        ],
    )

    (ref,) = ClaudeSource(tmp_path).list()

    assert ref.title == "Gerçek Başlık"
    assert ref.source == "claude"


def test_ai_title_yoksa_ilk_kullanici_mesaji_baslik_olur(tmp_path):
    _oturum_yaz(
        tmp_path,
        "-p",
        "s2",
        [{"type": "user", "message": {"role": "user", "content": "düşmanlar ölmüyor"}}],
    )

    (ref,) = ClaudeSource(tmp_path).list()

    assert ref.title == "düşmanlar ölmüyor"


def test_bozuk_satir_oturumu_dusurmez(tmp_path):
    yol = _oturum_yaz(
        tmp_path,
        "-p",
        "s3",
        [{"type": "user", "message": {"role": "user", "content": "sağlam"}}],
    )
    with yol.open("a", encoding="utf-8") as fh:
        fh.write("\n{bozuk json")

    (ref,) = ClaudeSource(tmp_path).list()

    assert ref.session_id == "s3"


def test_parca_listesi_iceren_mesaj_duz_metne_cevrilir(tmp_path):
    _oturum_yaz(
        tmp_path,
        "-p",
        "s4",
        [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "parça bir"}],
                },
            }
        ],
    )

    (turn,) = ClaudeSource(tmp_path).read("s4")

    assert turn.text == "parça bir"


def test_imlec_ve_limit_uygulanir(tmp_path):
    kayitlar = [
        {"type": "user", "message": {"role": "user", "content": f"m{i}"}} for i in range(5)
    ]
    _oturum_yaz(tmp_path, "-p", "s5", kayitlar)

    turlar = ClaudeSource(tmp_path).read("s5", cursor=1, limit=2)

    assert [t.text for t in turlar] == ["m1", "m2"]


def test_meta_ve_sidechain_kayitlari_atlanir(tmp_path):
    _oturum_yaz(
        tmp_path,
        "-p",
        "s6",
        [
            {"type": "user", "isMeta": True, "message": {"role": "user", "content": "meta"}},
            {"type": "user", "message": {"role": "user", "content": "gerçek"}},
        ],
    )

    turlar = ClaudeSource(tmp_path).read("s6")

    assert [t.text for t in turlar] == ["gerçek"]
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_claude.py`
Beklenen: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.history.claude_source'`

- [ ] **Step 3: Uygulamayı yaz**

`src/fusion_cli/history/claude_source.py`:

```python
"""Claude Code oturum geçmişi okuyucusu.

Claude her oturumu `~/.claude/projects/<slug>/<oturum>.jsonl` altında, satır başına
bir JSON kaydı olarak tutar. Slug, çalışma dizini yolundaki `/` karakterlerinin
`-` ile değiştirilmiş halidir.

İki tuzak vardır ve ikisi de gerçek veriden ölçüldü:

- `message.content` ya düz metin ya da parça listesidir; ikisi de karşılanmalı.
- Oturumların yalnızca bir kısmında `ai-title` kaydı bulunur (ölçüm: 47'de 13).
  Bu yüzden başlık çözümü basamaklıdır.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import SessionRef, Turn

#: Başlık olarak kullanılacak metnin en fazla uzunluğu.
TITLE_BUDGET = 60

#: Kullanıcı mesajı gibi görünen ama CLI'ın kendi ürettiği sarmalayıcılar. Bunlar
#: başlık olarak gösterilirse liste anlamsızlaşır.
_NOISE_PREFIXES = ("<local-command-caveat>", "<command-name>", "<command-message>")


def slug_for(root: Path) -> str:
    """Çalışma dizinini Claude'un proje dizini adına çevir."""
    return str(root).replace("/", "-")


def _text_of(message: dict[str, object]) -> str:
    """`content` alanını düz metne çevir. Parça listesi de düz metin de olabilir."""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p).strip()
    return ""


def _is_noise(text: str) -> bool:
    return text.startswith(_NOISE_PREFIXES)


class ClaudeSource:
    """Claude Code geçmişini okur. Hiçbir metodu istisna fırlatmaz."""

    name = "claude"

    def __init__(self, home: Path) -> None:
        self._home = home

    def _projects_root(self) -> Path:
        return self._home / ".claude" / "projects"

    def is_installed(self) -> bool:
        return self._projects_root().is_dir()

    def _session_paths(self, root: Path | None) -> list[Path]:
        base = self._projects_root()
        if not base.is_dir():
            return []
        if root is not None:
            wanted = base / slug_for(root)
            if wanted.is_dir():
                return sorted(wanted.glob("*.jsonl"))
        return sorted(base.glob("*/*.jsonl"))

    def list(self, root: Path | None = None) -> tuple[SessionRef, ...]:
        refs: list[SessionRef] = []
        for path in self._session_paths(root):
            ref = self._read_ref(path)
            if ref is not None:
                refs.append(ref)
        refs.sort(key=lambda r: r.updated_at, reverse=True)
        return tuple(refs)

    def _read_ref(self, path: Path) -> SessionRef | None:
        title = ""
        first_user = ""
        turn_count = 0
        for record in self._records(path):
            kind = record.get("type")
            if kind == "ai-title":
                title = str(record.get("aiTitle") or "").strip()
            elif kind in ("user", "assistant"):
                turn_count += 1
                if kind == "user" and not first_user:
                    text = _text_of(record.get("message", {}))
                    if text and not _is_noise(text):
                        first_user = text.splitlines()[0][:TITLE_BUDGET]
        try:
            updated_at = path.stat().st_mtime
        except OSError:
            return None
        return SessionRef(
            source=self.name,
            session_id=path.stem,
            title=title or first_user or path.stem,
            updated_at=updated_at,
            turn_count=turn_count,
        )

    def _records(self, path: Path):
        """Dosyayı satır satır oku; bozuk satırı atla. Bellekte tamamı tutulmaz."""
        try:
            handle = path.open(encoding="utf-8", errors="ignore")
        except OSError:
            return
        with handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(record, dict):
                    yield record

    def _find(self, session_id: str) -> Path | None:
        base = self._projects_root()
        if not base.is_dir():
            return None
        return next(iter(sorted(base.glob(f"*/{session_id}.jsonl"))), None)

    def read(self, session_id: str, cursor: int = 0, limit: int = 50) -> tuple[Turn, ...]:
        path = self._find(session_id)
        if path is None:
            return ()
        turns: list[Turn] = []
        seen = 0
        for record in self._records(path):
            if record.get("type") not in ("user", "assistant"):
                continue
            if record.get("isMeta") or record.get("isSidechain"):
                continue
            text = _text_of(record.get("message", {}))
            if not text:
                continue
            if seen < cursor:
                seen += 1
                continue
            turns.append(
                Turn(
                    role=str(record.get("type")),
                    text=text,
                    timestamp=_epoch(record.get("timestamp")),
                )
            )
            seen += 1
            if len(turns) >= limit:
                break
        return tuple(turns)


def _epoch(value: object) -> float:
    """ISO zaman damgasını unix saniyeye çevir. Çözülemezse 0 döner."""
    if not isinstance(value, str):
        return 0.0
    from datetime import datetime

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
```

- [ ] **Step 4: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_claude.py`
Beklenen: 9 passed

- [ ] **Step 5: Gerçek veriyle duman testi (elle, bir kez)**

```bash
.venv/bin/python -c "
from pathlib import Path
from fusion_cli.history.claude_source import ClaudeSource
s = ClaudeSource(Path.home())
refs = s.list()
print('oturum:', len(refs))
for r in refs[:3]:
    print(' ', r.title[:60], '|', r.turn_count, 'tur')
"
```
Beklenen: oturum sayısı 100'ün üzerinde, başlıklar okunabilir, çökme yok.

- [ ] **Step 6: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src/fusion_cli/history tests/test_history_claude.py
.venv/bin/ruff format src/fusion_cli/history tests/test_history_claude.py
.venv/bin/mypy src
.venv/bin/python -m pytest -q
git add src/fusion_cli/history/claude_source.py tests/test_history_claude.py
git commit -m "feat(history): Claude Code oturum geçmişini oku"
```

---

### Task 3: Codex okuyucusu

**Files:**
- Create: `src/fusion_cli/history/codex_source.py`
- Test: `tests/test_history_codex.py`

**Interfaces:**
- Consumes: `SessionRef`, `Turn` (Task 1).
- Produces: `CodexSource(home: Path)` — `name = "codex"`.

Gerçek biçim (ölçüldü): `~/.codex/session_index.jsonl` her satırda
`{"id","thread_name","updated_at"}` tutar — listeleme buradan ucuza yapılır.
İçerik `~/.codex/thread_history_1.sqlite` içindeki `thread_items` tablosundadır:
`thread_id`, `rollout_ordinal`, `item_type`, `item_json`. Kullanıcı mesajının metni
`item_json.content[0].text`, ajan mesajınınki `item_json.text` alanındadır.

- [ ] **Step 1: Testi yaz**

`tests/test_history_codex.py`:

```python
"""Codex/ChatGPT uygulaması geçmiş okuyucusu."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fusion_cli.history.codex_source import CodexSource

SEMA = """
CREATE TABLE thread_items (
    thread_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    rollout_ordinal INTEGER NOT NULL,
    created_at_ms INTEGER NOT NULL,
    item_json TEXT NOT NULL,
    item_type TEXT NOT NULL DEFAULT ''
);
"""


def _kur(home: Path, satirlar: list[tuple[str, int, str, dict]]) -> None:
    kok = home / ".codex"
    kok.mkdir(parents=True, exist_ok=True)
    baglanti = sqlite3.connect(kok / "thread_history_1.sqlite")
    baglanti.executescript(SEMA)
    for thread_id, ordinal, item_type, payload in satirlar:
        baglanti.execute(
            "INSERT INTO thread_items VALUES (?,?,?,?,?,?,?)",
            (thread_id, "t", f"i{ordinal}", ordinal, 0, json.dumps(payload), item_type),
        )
    baglanti.commit()
    baglanti.close()


def _indeks(home: Path, kayitlar: list[dict]) -> None:
    yol = home / ".codex" / "session_index.jsonl"
    yol.write_text("\n".join(json.dumps(k) for k in kayitlar), encoding="utf-8")


def test_iz_yoksa_kurulu_degil(tmp_path):
    assert CodexSource(tmp_path).is_installed() is False


def test_iz_varsa_kurulu(tmp_path):
    _kur(tmp_path, [])

    assert CodexSource(tmp_path).is_installed() is True


def test_indeksten_baslik_okunur(tmp_path):
    _kur(tmp_path, [])
    _indeks(
        tmp_path,
        [{"id": "th1", "thread_name": "Align Fusion CLI", "updated_at": "2026-08-27T13:13:49Z"}],
    )

    (ref,) = CodexSource(tmp_path).list()

    assert ref.title == "Align Fusion CLI"
    assert ref.source == "codex"


def test_kullanici_ve_ajan_mesajlari_okunur(tmp_path):
    _kur(
        tmp_path,
        [
            ("th1", 1, "userMessage", {"type": "userMessage", "content": [{"text": "soru"}]}),
            ("th1", 2, "agentMessage", {"type": "agentMessage", "text": "cevap"}),
        ],
    )

    turlar = CodexSource(tmp_path).read("th1")

    assert [(t.role, t.text) for t in turlar] == [("user", "soru"), ("assistant", "cevap")]


def test_imlec_ve_limit_uygulanir(tmp_path):
    _kur(
        tmp_path,
        [
            ("th1", i, "userMessage", {"type": "userMessage", "content": [{"text": f"m{i}"}]})
            for i in range(4)
        ],
    )

    turlar = CodexSource(tmp_path).read("th1", cursor=1, limit=2)

    assert [t.text for t in turlar] == ["m1", "m2"]


def test_bozuk_item_json_atlanir(tmp_path):
    _kur(tmp_path, [("th1", 1, "userMessage", {"type": "userMessage", "content": [{"text": "iyi"}]})])
    baglanti = sqlite3.connect(tmp_path / ".codex" / "thread_history_1.sqlite")
    baglanti.execute(
        "INSERT INTO thread_items VALUES ('th1','t','i9',9,0,'{bozuk','userMessage')"
    )
    baglanti.commit()
    baglanti.close()

    turlar = CodexSource(tmp_path).read("th1")

    assert [t.text for t in turlar] == ["iyi"]
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_codex.py`
Beklenen: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.history.codex_source'`

- [ ] **Step 3: Uygulamayı yaz**

`src/fusion_cli/history/codex_source.py`:

```python
"""Codex / ChatGPT uygulaması geçmiş okuyucusu.

İki ayrı yer okunur ve bu bilinçlidir:

- `session_index.jsonl` kimlik, başlık ve zaman tutar. Listeleme buradan yapılır;
  9 MB'lık veritabanını yalnızca liste basmak için açmak gereksizdir.
- `thread_history_1.sqlite` içindeki `thread_items` tablosu asıl içeriği tutar.
  `item_json` şeması tipe göre değişir: kullanıcı mesajı `content[0].text`,
  ajan mesajı düz `text` alanı kullanır.

Veritabanı salt okunur açılır (`mode=ro`): çalışan bir Codex oturumunun verisini
kilitlemek ya da bozmak kabul edilemez.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .models import SessionRef, Turn

#: Okunan tip → ortak rol eşlemesi. Listede olmayan tipler yok sayılır.
_ROLES = {"userMessage": "user", "agentMessage": "assistant"}


class CodexSource:
    """Codex geçmişini okur. Hiçbir metodu istisna fırlatmaz."""

    name = "codex"

    def __init__(self, home: Path) -> None:
        self._home = home

    def _db_path(self) -> Path:
        return self._home / ".codex" / "thread_history_1.sqlite"

    def is_installed(self) -> bool:
        return self._db_path().is_file()

    def _connect(self) -> sqlite3.Connection | None:
        path = self._db_path()
        if not path.is_file():
            return None
        try:
            return sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except sqlite3.Error:
            return None

    def list(self, root: Path | None = None) -> tuple[SessionRef, ...]:
        """Oturumları indeks dosyasından listele.

        `root` yok sayılır: Codex proje kökünü güvenilir biçimde saklamıyor
        (`project_roots` tablosu boş ölçüldü). Yanlış filtrelemektense hepsini
        göstermek dürüsttür.
        """
        index = self._home / ".codex" / "session_index.jsonl"
        refs: list[SessionRef] = []
        try:
            lines = index.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(record, dict) or not record.get("id"):
                continue
            refs.append(
                SessionRef(
                    source=self.name,
                    session_id=str(record["id"]),
                    title=str(record.get("thread_name") or record["id"]),
                    updated_at=_epoch(record.get("updated_at")),
                    turn_count=0,
                )
            )
        refs.sort(key=lambda r: r.updated_at, reverse=True)
        return tuple(refs)

    def read(self, session_id: str, cursor: int = 0, limit: int = 50) -> tuple[Turn, ...]:
        connection = self._connect()
        if connection is None:
            return ()
        turns: list[Turn] = []
        try:
            rows = connection.execute(
                "SELECT item_type, item_json, created_at_ms FROM thread_items "
                "WHERE thread_id = ? AND item_type IN ('userMessage','agentMessage') "
                "ORDER BY rollout_ordinal LIMIT ? OFFSET ?",
                (session_id, limit, cursor),
            ).fetchall()
        except sqlite3.Error:
            return ()
        finally:
            connection.close()
        for item_type, payload, created_ms in rows:
            text = _text_of(payload, str(item_type))
            if not text:
                continue
            turns.append(
                Turn(
                    role=_ROLES.get(str(item_type), "assistant"),
                    text=text,
                    timestamp=float(created_ms or 0) / 1000.0,
                )
            )
        return tuple(turns)


def _text_of(payload: object, item_type: str) -> str:
    """`item_json` içinden metni çıkar. Şema tipe göre değişir."""
    if not isinstance(payload, str):
        return ""
    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    if item_type == "agentMessage":
        return str(data.get("text") or "").strip()
    content = data.get("content")
    if isinstance(content, list):
        parts = [str(p.get("text", "")) for p in content if isinstance(p, dict)]
        return "\n".join(p for p in parts if p).strip()
    return ""


def _epoch(value: object) -> float:
    if not isinstance(value, str):
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
```

- [ ] **Step 4: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_codex.py`
Beklenen: 6 passed

- [ ] **Step 5: Gerçek veriyle duman testi**

```bash
.venv/bin/python -c "
from pathlib import Path
from fusion_cli.history.codex_source import CodexSource
s = CodexSource(Path.home())
refs = s.list()
print('oturum:', len(refs))
if refs:
    turlar = s.read(refs[0].session_id, limit=3)
    print('ilk oturum:', refs[0].title[:50], '| tur:', len(turlar))
"
```
Beklenen: oturum listelenir, ilk oturumdan 3 tur okunur, çökme yok.

- [ ] **Step 6: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src/fusion_cli/history tests/test_history_codex.py
.venv/bin/ruff format src/fusion_cli/history tests/test_history_codex.py
.venv/bin/mypy src
.venv/bin/python -m pytest -q
git add src/fusion_cli/history/codex_source.py tests/test_history_codex.py
git commit -m "feat(history): Codex oturum geçmişini oku"
```

---

### Task 4: Hermes okuyucusu

**Files:**
- Create: `src/fusion_cli/history/hermes_source.py`
- Test: `tests/test_history_hermes.py`

**Interfaces:**
- Consumes: `SessionRef`, `Turn` (Task 1).
- Produces: `HermesSource(home: Path)` — `name = "hermes"`.

Gerçek biçim (ölçüldü): `~/.hermes/state.db`, `sessions(id, title, cwd,
started_at, message_count)` ve `messages(session_id, role, content, timestamp)`.
Hermes `cwd` sakladığı için proje filtresi burada gerçekten çalışır.

- [ ] **Step 1: Testi yaz**

`tests/test_history_hermes.py`:

```python
"""Hermes geçmiş okuyucusu."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fusion_cli.history.hermes_source import HermesSource

SEMA = """
CREATE TABLE sessions (
    id TEXT PRIMARY KEY, source TEXT, title TEXT, cwd TEXT,
    started_at REAL NOT NULL, message_count INTEGER DEFAULT 0
);
CREATE TABLE messages (
    id TEXT PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, timestamp REAL
);
"""


def _kur(home: Path, oturumlar: list[tuple], mesajlar: list[tuple]) -> None:
    kok = home / ".hermes"
    kok.mkdir(parents=True, exist_ok=True)
    baglanti = sqlite3.connect(kok / "state.db")
    baglanti.executescript(SEMA)
    baglanti.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?)", oturumlar)
    baglanti.executemany("INSERT INTO messages VALUES (?,?,?,?,?)", mesajlar)
    baglanti.commit()
    baglanti.close()


def test_iz_yoksa_kurulu_degil(tmp_path):
    assert HermesSource(tmp_path).is_installed() is False


def test_baslik_ve_tur_sayisi_okunur(tmp_path):
    _kur(
        tmp_path,
        [("s1", "cli", "Pazar analizi", "/x/proje", 100.0, 2)],
        [("m1", "s1", "user", "soru", 101.0), ("m2", "s1", "assistant", "cevap", 102.0)],
    )

    (ref,) = HermesSource(tmp_path).list()

    assert ref.title == "Pazar analizi"
    assert ref.turn_count == 2
    assert ref.source == "hermes"


def test_baslik_yoksa_ilk_kullanici_mesaji_kullanilir(tmp_path):
    _kur(
        tmp_path,
        [("s1", "cli", None, "/x", 100.0, 1)],
        [("m1", "s1", "user", "başlıksız oturum", 101.0)],
    )

    (ref,) = HermesSource(tmp_path).list()

    assert ref.title == "başlıksız oturum"


def test_proje_koku_verilince_o_klasor_once_gelir(tmp_path):
    _kur(
        tmp_path,
        [
            ("s1", "cli", "başka", "/baska", 100.0, 0),
            ("s2", "cli", "hedef", "/hedef", 50.0, 0),
        ],
        [],
    )

    refs = HermesSource(tmp_path).list(Path("/hedef"))

    assert refs[0].title == "hedef"


def test_imlec_ve_limit_uygulanir(tmp_path):
    _kur(
        tmp_path,
        [("s1", "cli", "t", "/x", 100.0, 4)],
        [(f"m{i}", "s1", "user", f"m{i}", 100.0 + i) for i in range(4)],
    )

    turlar = HermesSource(tmp_path).read("s1", cursor=1, limit=2)

    assert [t.text for t in turlar] == ["m1", "m2"]
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_hermes.py`
Beklenen: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.history.hermes_source'`

- [ ] **Step 3: Uygulamayı yaz**

`src/fusion_cli/history/hermes_source.py`:

```python
"""Hermes geçmiş okuyucusu.

Hermes `~/.hermes/state.db` içinde `sessions` ve `messages` tablolarını tutar.
Diğer iki kaynaktan farklı olarak `sessions.cwd` sütunu vardır; bu yüzden proje
filtresi burada gerçekten anlamlıdır ve uygulanır.

Veritabanı salt okunur açılır: çalışan bir Hermes oturumunun verisi kilitlenmemeli.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import SessionRef, Turn

#: Başlık olarak kullanılacak metnin en fazla uzunluğu.
TITLE_BUDGET = 60


class HermesSource:
    """Hermes geçmişini okur. Hiçbir metodu istisna fırlatmaz."""

    name = "hermes"

    def __init__(self, home: Path) -> None:
        self._home = home

    def _db_path(self) -> Path:
        return self._home / ".hermes" / "state.db"

    def is_installed(self) -> bool:
        return self._db_path().is_file()

    def _connect(self) -> sqlite3.Connection | None:
        path = self._db_path()
        if not path.is_file():
            return None
        try:
            return sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except sqlite3.Error:
            return None

    def list(self, root: Path | None = None) -> tuple[SessionRef, ...]:
        connection = self._connect()
        if connection is None:
            return ()
        try:
            rows = connection.execute(
                "SELECT s.id, s.title, s.cwd, s.started_at, s.message_count, "
                "(SELECT content FROM messages m WHERE m.session_id = s.id "
                " AND m.role = 'user' ORDER BY m.timestamp LIMIT 1) "
                "FROM sessions s ORDER BY s.started_at DESC"
            ).fetchall()
        except sqlite3.Error:
            return ()
        finally:
            connection.close()

        refs = [
            SessionRef(
                source=self.name,
                session_id=str(row[0]),
                title=_title(row[1], row[5], str(row[0])),
                updated_at=float(row[3] or 0.0),
                turn_count=int(row[4] or 0),
            )
            for row in rows
        ]
        if root is None:
            return tuple(refs)
        wanted = str(root)
        cwds = {str(row[0]): (row[2] or "") for row in rows}
        # Eşleşenler öne alınır; sıralamanın kendisi bozulmaz.
        refs.sort(key=lambda r: cwds.get(r.session_id, "") != wanted)
        return tuple(refs)

    def read(self, session_id: str, cursor: int = 0, limit: int = 50) -> tuple[Turn, ...]:
        connection = self._connect()
        if connection is None:
            return ()
        try:
            rows = connection.execute(
                "SELECT role, content, timestamp FROM messages "
                "WHERE session_id = ? ORDER BY timestamp LIMIT ? OFFSET ?",
                (session_id, limit, cursor),
            ).fetchall()
        except sqlite3.Error:
            return ()
        finally:
            connection.close()
        return tuple(
            Turn(role=str(role or "assistant"), text=str(content or "").strip(),
                 timestamp=float(ts or 0.0))
            for role, content, ts in rows
            if str(content or "").strip()
        )


def _title(stored: object, first_user: object, fallback: str) -> str:
    """Başlık çözümü: kayıtlı başlık → ilk kullanıcı mesajı → kimlik."""
    text = str(stored or "").strip()
    if text:
        return text[:TITLE_BUDGET]
    text = str(first_user or "").strip()
    if text:
        return text.splitlines()[0][:TITLE_BUDGET]
    return fallback
```

- [ ] **Step 4: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_hermes.py`
Beklenen: 5 passed

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src/fusion_cli/history tests/test_history_hermes.py
.venv/bin/ruff format src/fusion_cli/history tests/test_history_hermes.py
.venv/bin/mypy src
.venv/bin/python -m pytest -q
git add src/fusion_cli/history/hermes_source.py tests/test_history_hermes.py
git commit -m "feat(history): Hermes oturum geçmişini oku"
```

---

### Task 5: Kaynak kayıt defteri ve kurulu tespiti

**Files:**
- Create: `src/fusion_cli/history/registry.py`
- Modify: `src/fusion_cli/history/__init__.py`
- Test: `tests/test_history_registry.py`

**Interfaces:**
- Consumes: `ClaudeSource`, `CodexSource`, `HermesSource` (Task 2-4).
- Produces: `all_sources(home: Path) -> tuple[HistorySource, ...]`,
  `available_sources(home: Path) -> tuple[HistorySource, ...]` (yalnızca kurulu),
  `source_by_name(home: Path, name: str) -> HistorySource | None`,
  `recent_sessions(home: Path, root: Path, limit: int = 5) -> tuple[SessionRef, ...]`.

- [ ] **Step 1: Testi yaz**

`tests/test_history_registry.py`:

```python
"""Kurulu geçmiş kaynaklarının tespiti."""

from __future__ import annotations

import json

from fusion_cli.history.registry import available_sources, recent_sessions, source_by_name


def _claude_kur(home, slug="-x", session_id="s1", metin="merhaba", mtime=None):
    hedef = home / ".claude" / "projects" / slug
    hedef.mkdir(parents=True, exist_ok=True)
    yol = hedef / f"{session_id}.jsonl"
    yol.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": metin}}),
        encoding="utf-8",
    )
    if mtime is not None:
        import os

        os.utime(yol, (mtime, mtime))
    return yol


def test_hicbir_arac_yoksa_kaynak_yok(tmp_path):
    assert available_sources(tmp_path) == ()


def test_yalniz_kurulu_kaynak_donder(tmp_path):
    _claude_kur(tmp_path)

    adlar = [s.name for s in available_sources(tmp_path)]

    assert adlar == ["claude"]


def test_ada_gore_cozer(tmp_path):
    _claude_kur(tmp_path)

    assert source_by_name(tmp_path, "claude") is not None
    assert source_by_name(tmp_path, "hermes") is None


def test_son_oturumlar_limitle_kirpilir(tmp_path):
    for i in range(7):
        _claude_kur(tmp_path, session_id=f"s{i}", metin=f"m{i}", mtime=1000 + i)

    refs = recent_sessions(tmp_path, tmp_path / "proje", limit=5)

    assert len(refs) == 5


def test_son_oturumlar_yeniden_eskiye_sirali(tmp_path):
    _claude_kur(tmp_path, session_id="eski", metin="eski", mtime=1000)
    _claude_kur(tmp_path, session_id="yeni", metin="yeni", mtime=2000)

    refs = recent_sessions(tmp_path, tmp_path / "proje")

    assert refs[0].session_id == "yeni"
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_registry.py`
Beklenen: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.history.registry'`

- [ ] **Step 3: Uygulamayı yaz**

`src/fusion_cli/history/registry.py`:

```python
"""Kurulu geçmiş kaynaklarını bulur ve ada göre çözer.

Bir kaynak yalnızca izi varsa etkinleşir. Tespit tek bir varlık kontrolüdür:
dosya açılmaz, sorgu çalıştırılmaz. Kurulmamış bir aracın komutu HİÇ var olmaz —
gri gösterilmez, "kurulu değil" demez; kayıt defterine hiç girmez.
"""

from __future__ import annotations

from pathlib import Path

from .claude_source import ClaudeSource
from .codex_source import CodexSource
from .hermes_source import HermesSource
from .models import HistorySource, SessionRef

#: Açılış listesinde gösterilecek en fazla oturum.
RECENT_LIMIT = 5


def all_sources(home: Path) -> tuple[HistorySource, ...]:
    """Bilinen tüm kaynaklar, kurulu olsun olmasın."""
    return (ClaudeSource(home), CodexSource(home), HermesSource(home))


def available_sources(home: Path) -> tuple[HistorySource, ...]:
    """Yalnızca makinede izi bulunan kaynaklar."""
    return tuple(source for source in all_sources(home) if source.is_installed())


def source_by_name(home: Path, name: str) -> HistorySource | None:
    """Kurulu kaynağı adıyla çöz. Kurulu değilse `None`."""
    wanted = name.strip().lower()
    return next((s for s in available_sources(home) if s.name == wanted), None)


def recent_sessions(
    home: Path, root: Path, limit: int = RECENT_LIMIT
) -> tuple[SessionRef, ...]:
    """Tüm kurulu kaynaklardan en son oturumlar, karışık ve zamana göre sıralı."""
    collected: list[SessionRef] = []
    for source in available_sources(home):
        collected.extend(source.list(root))
    collected.sort(key=lambda ref: ref.updated_at, reverse=True)
    return tuple(collected[:limit])
```

`src/fusion_cli/history/__init__.py` sonuna ekle:

```python
from .digest import build_digest  # noqa: E402  (döngüsel import'u önlemek için sonda)
from .models import SessionRef, Turn  # noqa: E402
from .registry import available_sources, recent_sessions, source_by_name  # noqa: E402

__all__ = [
    "SessionRef",
    "Turn",
    "available_sources",
    "build_digest",
    "recent_sessions",
    "source_by_name",
]
```

**Not:** `build_digest` Task 6'da yazılıyor. Bu görevde `__init__.py`'ye YALNIZCA
`models` ve `registry` satırlarını ekle; `digest` satırını ve `__all__` içindeki
`"build_digest"` girdisini Task 6'da ekle. Aksi halde bu görevin testleri import
hatasıyla düşer.

- [ ] **Step 4: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_registry.py`
Beklenen: 5 passed

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src/fusion_cli/history tests/test_history_registry.py
.venv/bin/ruff format src/fusion_cli/history tests/test_history_registry.py
.venv/bin/mypy src
.venv/bin/python -m pytest -q
git add src/fusion_cli/history tests/test_history_registry.py
git commit -m "feat(history): kurulu geçmiş kaynaklarını tespit et"
```

---

### Task 6: Künye üretimi ve sır sayımı

**Files:**
- Create: `src/fusion_cli/history/digest.py`
- Modify: `src/fusion_cli/history/__init__.py`
- Test: `tests/test_history_digest.py`

**Interfaces:**
- Consumes: `SessionRef`, `Turn`, `HistorySource` (Task 1-5).
- Produces: `Digest(text: str, secret_count: int)`,
  `build_digest(source: HistorySource, ref: SessionRef, max_lines: int = 40) -> Digest`,
  `count_secrets(text: str) -> int`.

Künye deterministiktir: model çağrısı içermez, aynı girdi her zaman aynı çıktıyı
verir. Sır **sayılır ama maskelenmez** (spec "Sırlar").

- [ ] **Step 1: Testi yaz**

`tests/test_history_digest.py`:

```python
"""Oturum künyesi ve sır sayımı."""

from __future__ import annotations

from pathlib import Path

from fusion_cli.history.digest import build_digest, count_secrets
from fusion_cli.history.models import SessionRef, Turn


class _SahteKaynak:
    name = "claude"

    def __init__(self, turlar):
        self._turlar = turlar

    def is_installed(self):
        return True

    def list(self, root=None):
        return ()

    def read(self, session_id, cursor=0, limit=50):
        return tuple(self._turlar[cursor : cursor + limit])


def _ref():
    return SessionRef(
        source="claude", session_id="s1", title="Test", updated_at=0.0, turn_count=2
    )


def test_kunye_kullanici_mesajlarini_listeler():
    kaynak = _SahteKaynak(
        [Turn("user", "ilk istek"), Turn("assistant", "cevap"), Turn("user", "ikinci istek")]
    )

    digest = build_digest(kaynak, _ref())

    assert "ilk istek" in digest.text
    assert "ikinci istek" in digest.text


def test_kunye_ajan_cevaplarini_listelemez():
    kaynak = _SahteKaynak([Turn("user", "istek"), Turn("assistant", "uzun ajan cevabı")])

    digest = build_digest(kaynak, _ref())

    assert "uzun ajan cevabı" not in digest.text


def test_kunye_deterministik():
    kaynak = _SahteKaynak([Turn("user", "a"), Turn("user", "b")])

    assert build_digest(kaynak, _ref()).text == build_digest(kaynak, _ref()).text


def test_sir_sayilir_ama_maskelenmez():
    kaynak = _SahteKaynak([Turn("user", "ANTHROPIC_API_KEY=sk-ant-0123456789abcdefghij")])

    digest = build_digest(kaynak, _ref())

    assert digest.secret_count >= 1
    assert "sk-ant-0123456789abcdefghij" in digest.text


def test_sirsiz_metinde_sayim_sifir():
    assert count_secrets("burada hiçbir şey yok") == 0


def test_bilinen_desenler_sayilir():
    assert count_secrets("Bearer abcdefghijklmnopqrstuvwx") >= 1
    assert count_secrets("DB_PASSWORD=cokgizli123") >= 1
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_digest.py`
Beklenen: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.history.digest'`

- [ ] **Step 3: Uygulamayı yaz**

`src/fusion_cli/history/digest.py`:

```python
"""Oturum künyesi: devralmadan önce basılan ucuz triyaj özeti.

Künye DETERMİNİSTİKTİR — model çağrısı içermez, aynı girdi her zaman aynı çıktıyı
verir. Amacı oturumun tamamını bağlama yüklemek değil, ajana NEREYE bakacağını
söylemektir; ayrıntı `read_session` ile çekilir.

Yalnızca kullanıcı mesajları listelenir: ajan cevapları uzundur ve triyaj için
değeri düşüktür. İşin ne olduğunu kullanıcının kendi cümleleri anlatır.

Sırlar SAYILIR ama MASKELENMEZ. Bu bilinçli bir üründür kararıdır: maskeleme
devralınan bağlamı sessizce bozabilir. Sayım yalnızca kullanıcıyı uyarmak içindir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import HistorySource, SessionRef

#: Künyede gösterilecek en fazla kullanıcı mesajı.
MAX_LINES = 40
#: Künyedeki tek bir satırın en fazla uzunluğu.
LINE_BUDGET = 120
#: Künye üretilirken kaynaktan çekilecek en fazla tur.
SCAN_LIMIT = 400

#: Sır ARAMA desenleri. Amaç maskelemek değil saymaktır; bu yüzden geniş tutulur,
#: yanlış pozitif kabul edilebilir — kullanıcıya "bak" demek yeterlidir.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(sk-[A-Za-z0-9]{20,}|nvapi-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{30,})"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"),
    re.compile(r"\b[A-Z][A-Z0-9_]{3,}_(KEY|TOKEN|SECRET|PASSWORD)\s*=\s*\S{8,}"),
    re.compile(r"BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY"),
)


@dataclass(frozen=True, slots=True)
class Digest:
    """Bağlama girecek künye metni ve bulunan sır sayısı."""

    text: str
    secret_count: int


def count_secrets(text: str) -> int:
    """Metindeki sır benzeri dizgileri say. İçeriği DEĞİŞTİRMEZ."""
    return sum(len(pattern.findall(text)) for pattern in _SECRET_PATTERNS)


def build_digest(
    source: HistorySource, ref: SessionRef, max_lines: int = MAX_LINES
) -> Digest:
    """Bir oturumun deterministik künyesini üret."""
    turns = source.read(ref.session_id, cursor=0, limit=SCAN_LIMIT)
    secret_count = sum(count_secrets(turn.text) for turn in turns)

    lines = [
        f"<devralinan_oturum kaynak=\"{ref.source}\" kimlik=\"{ref.session_id}\">",
        f"başlık: {ref.title}",
        f"tur sayısı: {len(turns)}",
        "kullanıcının istekleri (sırayla):",
    ]
    shown = 0
    for index, turn in enumerate(turns):
        if turn.role != "user":
            continue
        if shown >= max_lines:
            lines.append("  […daha fazlası var, read_session ile devamını oku…]")
            break
        summary = " ".join(turn.text.split())[:LINE_BUDGET]
        lines.append(f"  [{index}] {summary}")
        shown += 1
    lines.append("</devralinan_oturum>")
    return Digest(text="\n".join(lines), secret_count=secret_count)
```

`src/fusion_cli/history/__init__.py` — Task 5'te bırakılan yeri tamamla:

```python
from .digest import build_digest  # noqa: E402
```

ve `__all__` listesine `"build_digest"` ekle.

- [ ] **Step 4: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_digest.py`
Beklenen: 6 passed

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src/fusion_cli/history tests/test_history_digest.py
.venv/bin/ruff format src/fusion_cli/history tests/test_history_digest.py
.venv/bin/mypy src
.venv/bin/python -m pytest -q
git add src/fusion_cli/history tests/test_history_digest.py
git commit -m "feat(history): oturum künyesi üret ve sırları say"
```

---

### Task 7: Dinamik `/resume<kaynak>` komutları

**Files:**
- Modify: `src/fusion_cli/cli/repl/commands.py` (`build_registry`, yeni işleyici)
- Modify: `src/fusion_cli/ui/messages.py` (metinler)
- Modify: `src/fusion_cli/cli/repl/state.py` (devralınan künyeyi taşıyan alan)
- Test: `tests/test_history_commands.py`

**Interfaces:**
- Consumes: `available_sources`, `source_by_name`, `build_digest` (Task 5-6).
- Produces: `ReplState.pending_digest: str | None` — devralınan künye. Task 9 ve
  ajan turu bunu okur. `build_registry(home: Path | None = None)` imzası genişler.

Bugün `build_registry()` yalnızca sabit `_COMMANDS` demetini okuyor. Kurulu
kaynaklara göre komut eklemek için imzası genişletilir; `home` verilmezse
davranış bugünküyle birebir aynıdır (mevcut çağrılar kırılmaz).

- [ ] **Step 1: Testi yaz**

`tests/test_history_commands.py`:

```python
"""Kurulu kaynaklara göre eklenen /resume komutları."""

from __future__ import annotations

import json

from fusion_cli.cli.repl.commands import build_registry


def _claude_kur(home):
    hedef = home / ".claude" / "projects" / "-x"
    hedef.mkdir(parents=True, exist_ok=True)
    (hedef / "s1.jsonl").write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "merhaba"}}),
        encoding="utf-8",
    )


def test_home_verilmezse_resume_komutu_yok():
    registry = build_registry()

    assert registry.get("resumeclaude") is None


def test_kurulu_kaynak_icin_komut_eklenir(tmp_path):
    _claude_kur(tmp_path)

    registry = build_registry(tmp_path)

    assert registry.get("resumeclaude") is not None


def test_kurulmamis_kaynak_icin_komut_hic_yok(tmp_path):
    _claude_kur(tmp_path)

    registry = build_registry(tmp_path)

    assert registry.get("resumehermes") is None
    assert "/resumehermes" not in registry.completion_words()


def test_komut_tamamlamada_gorunur(tmp_path):
    _claude_kur(tmp_path)

    registry = build_registry(tmp_path)

    assert "/resumeclaude" in registry.completion_words()


def test_komut_gecmis_grubunda(tmp_path):
    _claude_kur(tmp_path)

    komut = build_registry(tmp_path).get("resumeclaude")

    assert komut is not None
    assert komut.group == "Geçmiş"
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_commands.py`
Beklenen: FAIL — `TypeError: build_registry() takes 0 positional arguments but 1 was given`

- [ ] **Step 3: Metin sabitlerini ekle**

`src/fusion_cli/ui/messages.py` içine, komut açıklamaları bölümüne:

```python
CMD_RESUME = "{source} oturum geçmişinden devral"
HISTORY_EMPTY = "Bu kaynakta devralınacak oturum bulunamadı."
HISTORY_PICK_TITLE = "Hangi oturumdan devam edilsin?"
HISTORY_RESUMED = "Devralındı: {title}"
HISTORY_SECRETS_FOUND = (
    "⚠ Bu oturumda {count} anahtar/token göründü. Bunları değiştirmeni öneririm."
)
HISTORY_RECENT_TITLE = "son oturumlar"
```

- [ ] **Step 4: `ReplState`'e alan ekle**

`src/fusion_cli/cli/repl/state.py` içinde, `reminders` alanının hemen ardına:

```python
    #: Devralınan oturumun künyesi. Bir sonraki turda sistem bağlamına eklenir.
    pending_digest: str | None = None
```

- [ ] **Step 5: Komut işleyicisini ve dinamik kaydı yaz**

`src/fusion_cli/cli/repl/commands.py` — import bölümüne:

```python
from ...history import build_digest, available_sources, source_by_name
```

İşleyiciler bölümüne (`_agents` fonksiyonunun ardına):

```python
def _resume(source_name: str) -> Handler:
    """`/resume<kaynak>` işleyicisi üret. Kaynak adı kapatmada sabitlenir."""

    def _handler(state: ReplState, argument: str) -> str:
        from ...ui.picker import Choice, pick

        source = source_by_name(state.home, source_name)
        if source is None:
            return messages.HISTORY_EMPTY
        refs = source.list(state.root)
        if not refs:
            return messages.HISTORY_EMPTY
        choices = [
            Choice(ref.session_id, ref.title, _when(ref.updated_at)) for ref in refs[:50]
        ]
        chosen = pick(choices, title=messages.HISTORY_PICK_TITLE)
        if chosen is None:
            return ""
        ref = next(r for r in refs if r.session_id == chosen)
        digest = build_digest(source, ref)
        state.pending_digest = digest.text
        line = messages.HISTORY_RESUMED.format(title=ref.title)
        if digest.secret_count:
            line += "\n" + messages.HISTORY_SECRETS_FOUND.format(count=digest.secret_count)
        return line

    return _handler


def _when(epoch: float) -> str:
    """Zaman damgasını listede gösterilecek kısa biçime çevir."""
    from datetime import datetime

    if not epoch:
        return ""
    return datetime.fromtimestamp(epoch).strftime("%d/%m %H:%M")
```

`build_registry` fonksiyonunu değiştir:

```python
def build_registry(home: Path | None = None) -> CommandRegistry:
    """Yerleşik komutların tamamını içeren defter.

    `home` verilirse makinede izi bulunan her geçmiş kaynağı için bir
    `/resume<kaynak>` komutu EKLENİR. Kurulu olmayan aracın komutu hiç var olmaz:
    tamamlamada da yardımda da görünmez.
    """
    registry = CommandRegistry()
    for command in _COMMANDS:
        registry.register(command)
    if home is not None:
        for source in available_sources(home):
            registry.register(
                SlashCommand(
                    f"resume{source.name}",
                    messages.CMD_RESUME.format(source=source.name),
                    _resume(source.name),
                    group="Geçmiş",
                )
            )
    return registry
```

`Path` import'u dosyada yoksa üste ekle:

```python
from pathlib import Path
```

`ReplState`'te `home` alanı YOKTUR; ekle (`state.py`, `root` alanının ardına):

```python
    #: Geçmiş kaynaklarının aranacağı ev dizini. Test enjekte edebilsin diye alandır.
    home: Path = field(default_factory=Path.home)
```

Aynı dosyada `__post_init__` bugün `CapabilityRegistry(Path.home(), self.root)`
diye sabit çağırıyor (`state.py:107`). Bunu `CapabilityRegistry(self.home, self.root)`
yap: ev dizini artık tek bir yerden geliyor ve testler gerçek `~` dizinine
bağımlı kalmıyor. Bu değişiklik davranışı bozmaz — varsayılan yine `Path.home()`.

- [ ] **Step 6: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_commands.py`
Beklenen: 5 passed

- [ ] **Step 7: Mevcut testlerin kırılmadığını doğrula**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_repl.py`
Beklenen: hepsi geçer — `build_registry()` argümansız çağrıldığında davranış değişmedi.

- [ ] **Step 8: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format src/fusion_cli/cli/repl/commands.py src/fusion_cli/ui/messages.py \
  src/fusion_cli/cli/repl/state.py tests/test_history_commands.py
.venv/bin/mypy src
.venv/bin/python -m pytest -q
git add src/fusion_cli/cli/repl/commands.py src/fusion_cli/ui/messages.py \
  src/fusion_cli/cli/repl/state.py tests/test_history_commands.py
git commit -m "feat(repl): kurulu araçlar için devralma komutları ekle"
```

---

### Task 8: `read_session` ajan aracı

**Files:**
- Modify: `src/fusion_cli/engines/agent/engine_tools.py`
- Test: `tests/test_history_tool.py`

**Interfaces:**
- Consumes: `source_by_name` (Task 5), `Turn` (Task 1).
- Produces: `read_session` aracı — parametreler `source` (str), `session_id` (str),
  `cursor` (int, varsayılan 0), `limit` (int, varsayılan 20).

- [ ] **Step 1: Testi yaz**

`tests/test_history_tool.py`:

```python
"""read_session ajan aracı."""

from __future__ import annotations

import json

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.engine_tools import build_history_tool

# Not: pyproject'te `asyncio_mode = "auto"` — `@pytest.mark.asyncio` GEREKMEZ.


def _claude_kur(home, mesajlar):
    hedef = home / ".claude" / "projects" / "-x"
    hedef.mkdir(parents=True, exist_ok=True)
    (hedef / "s1.jsonl").write_text(
        "\n".join(
            json.dumps({"type": "user", "message": {"role": "user", "content": m}})
            for m in mesajlar
        ),
        encoding="utf-8",
    )


async def test_arac_turlari_dondurur(tmp_path):
    _claude_kur(tmp_path, ["birinci", "ikinci"])
    tool = build_history_tool(tmp_path)

    sonuc = await tool.run({"source": "claude", "session_id": "s1"}, ToolContext(root=tmp_path))

    assert "birinci" in sonuc.output
    assert "ikinci" in sonuc.output


async def test_bilinmeyen_kaynak_hata_dondurur(tmp_path):
    _claude_kur(tmp_path, ["m"])
    tool = build_history_tool(tmp_path)

    sonuc = await tool.run({"source": "yok", "session_id": "s1"}, ToolContext(root=tmp_path))

    assert sonuc.ok is False


async def test_bilinmeyen_oturum_hata_dondurur(tmp_path):
    _claude_kur(tmp_path, ["m"])
    tool = build_history_tool(tmp_path)

    sonuc = await tool.run(
        {"source": "claude", "session_id": "olmayan"}, ToolContext(root=tmp_path)
    )

    assert sonuc.ok is False


async def test_imlec_gecirilir(tmp_path):
    _claude_kur(tmp_path, ["m0", "m1", "m2"])
    tool = build_history_tool(tmp_path)

    sonuc = await tool.run(
        {"source": "claude", "session_id": "s1", "cursor": 1, "limit": 1},
        ToolContext(root=tmp_path),
    )

    assert "m1" in sonuc.output
    assert "m0" not in sonuc.output
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_tool.py`
Beklenen: FAIL — `ImportError: cannot import name 'build_history_tool'`

- [ ] **Step 3: Uygulamayı yaz**

`src/fusion_cli/engines/agent/engine_tools.py` sonuna:

```python
def build_history_tool(home: Path) -> Tool:
    """`read_session` — devralınan oturumun ayrıntısını imleçle oku.

    Künye ajana NEREYE bakacağını söyler; bu araç oraya BAKMASINI sağlar. Oturumun
    tamamı hiçbir zaman bağlama yüklenmez: medyan bir oturum 1,3 MB'tır.
    """

    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        from ...history import source_by_name

        source_name = args.get("source")
        session_id = args.get("session_id")
        if not isinstance(source_name, str) or not isinstance(session_id, str):
            return ToolResult.failure("'source' ve 'session_id' metin olmalı.")
        source = source_by_name(home, source_name)
        if source is None:
            return ToolResult.failure(f"Bilinmeyen ya da kurulu olmayan kaynak: {source_name}")
        cursor = args.get("cursor")
        limit = args.get("limit")
        turns = source.read(
            session_id,
            cursor=cursor if isinstance(cursor, int) and cursor >= 0 else 0,
            limit=limit if isinstance(limit, int) and 0 < limit <= 100 else 20,
        )
        if not turns:
            return ToolResult.failure(
                f"Oturum bulunamadı ya da bu imleçte tur yok: {session_id}"
            )
        return ToolResult("\n\n".join(f"[{t.role}] {t.text}" for t in turns))

    return Tool(
        name="read_session",
        description="Devralınan bir oturumun turlarını imleçle oku. Künyede gördüğün "
        "satır numarasını 'cursor' olarak ver; oturumun tamamını çekmeye KALKMA.",
        parameters={
            "type": "object",
            "properties": {
                "source": _STRING,
                "session_id": _STRING,
                "cursor": {"type": "integer"},
                "limit": {"type": "integer"},
            },
            "required": ["source", "session_id"],
        },
        run=_run,
    )
```

**Dikkat — mevcut kodun sözleşmesi:** `Tool` alanının adı `run`'dır, `handler`
değil; executor İKİ parametre alır (`args: ToolArgs, context: ToolContext`) ve
defterin metodu `.register()`'dır, `.add()` değil. Desen `_ask_user_tool`
(`engine_tools.py:216`) ile birebir aynıdır.

Dosyanın üstünde `Path` import'u yoksa ekle:

```python
from pathlib import Path
```

Aracı kayıt defterine bağla — `build_agent_registry` içinde, `_ask_user_tool`
kaydının hemen ardına (`engine_tools.py:76` civarı):

```python
    if deps.home is not None:
        extended.register(build_history_tool(deps.home))
```

`AgentDeps` (`src/fusion_cli/engines/agent/loop.py:229`) içine, `capabilities`
alanının ardına ekle — dosyadaki mevcut yorum üslubunu izler:

```python
    #: Geçmiş kaynaklarının aranacağı ev dizini. Yoksa `read_session` aracı hiç sunulmaz.
    home: Path | None = None
```

`build_agent_registry` imzası DEĞİŞMEZ: bağımlılık `deps` üzerinden taşınır,
çünkü mevcut imza `(deps, *, depth, run_agent)` ve çağıranları var. `home`
verilmezse araç sunulmaz ve bugünkü davranış korunur — bu, `asker`,
`code_index` ve `capabilities` alanlarının izlediği desenin aynısıdır.

- [ ] **Step 4: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_tool.py`
Beklenen: 4 passed

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format src/fusion_cli/engines/agent/engine_tools.py tests/test_history_tool.py
.venv/bin/mypy src
.venv/bin/python -m pytest -q
git add src/fusion_cli/engines/agent/engine_tools.py tests/test_history_tool.py
git commit -m "feat(agent): devralınan oturumu okuyan read_session aracını ekle"
```

---

### Task 9: Açılışta son oturum listesi

**Files:**
- Modify: `src/fusion_cli/cli/repl/loop.py` (banner sonrası)
- Modify: `src/fusion_cli/ui/messages.py`
- Test: `tests/test_history_startup.py`

**Interfaces:**
- Consumes: `recent_sessions` (Task 5), `HISTORY_RECENT_TITLE` (Task 7).
- Produces: `render_recent(home: Path, root: Path) -> str` — boş dizge basılmaz.

- [ ] **Step 1: Testi yaz**

`tests/test_history_startup.py`:

```python
"""Açılıştaki son oturum listesi."""

from __future__ import annotations

import json
import os

from fusion_cli.cli.repl.history_view import render_recent


def _claude_kur(home, session_id, metin, mtime):
    hedef = home / ".claude" / "projects" / "-x"
    hedef.mkdir(parents=True, exist_ok=True)
    yol = hedef / f"{session_id}.jsonl"
    yol.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": metin}}),
        encoding="utf-8",
    )
    os.utime(yol, (mtime, mtime))


def test_oturum_yoksa_bos_doner(tmp_path):
    assert render_recent(tmp_path, tmp_path / "proje") == ""


def test_oturumlar_kaynak_etiketiyle_listelenir(tmp_path):
    _claude_kur(tmp_path, "s1", "ilk iş", 1000)

    cikti = render_recent(tmp_path, tmp_path / "proje")

    assert "ilk iş" in cikti
    assert "claude" in cikti


def test_en_fazla_bes_oturum_gosterilir(tmp_path):
    for i in range(9):
        _claude_kur(tmp_path, f"s{i}", f"iş {i}", 1000 + i)

    cikti = render_recent(tmp_path, tmp_path / "proje")

    assert len([s for s in cikti.splitlines() if s.startswith("  ")]) == 5
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_startup.py`
Beklenen: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.cli.repl.history_view'`

- [ ] **Step 3: Uygulamayı yaz**

`src/fusion_cli/cli/repl/history_view.py`:

```python
"""Açılışta basılan son oturum listesi.

Amaç geçmişi HATIRLATMAKTIR, tam bir tarayıcı sunmak değil: tam liste
`/resume<kaynak>` ile açılır. Oturum yoksa hiçbir şey basılmaz — boş bir başlık
gürültüdür ve açılış ekranını uzatır.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ...history import recent_sessions
from ...ui import messages


def render_recent(home: Path, root: Path) -> str:
    """Son oturumları tek bir metin bloğu olarak döndür. Yoksa boş dizge."""
    refs = recent_sessions(home, root)
    if not refs:
        return ""
    lines = [messages.HISTORY_RECENT_TITLE]
    for ref in refs:
        when = datetime.fromtimestamp(ref.updated_at).strftime("%d/%m %H:%M") if ref.updated_at else ""
        lines.append(f"  {ref.source:<7} {when:<12} {ref.title}")
    return "\n".join(lines)
```

`src/fusion_cli/cli/repl/loop.py` — açılış banner'ının hemen ardına
(`banner.print_welcome(console, session_info(state))`, `loop.py:112`):

```python
    recent = render_recent(state.home, state.root)
    if recent:
        console.print(recent, highlight=False)
        console.print()
```

ve dosyanın import bölümüne:

```python
from .history_view import render_recent
```

- [ ] **Step 4: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_startup.py`
Beklenen: 3 passed

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format src/fusion_cli/cli/repl/history_view.py src/fusion_cli/cli/repl/loop.py \
  tests/test_history_startup.py
.venv/bin/mypy src
.venv/bin/python -m pytest -q
git add src/fusion_cli/cli/repl/history_view.py src/fusion_cli/cli/repl/loop.py \
  tests/test_history_startup.py
git commit -m "feat(repl): açılışta son oturumları göster"
```

---

### Task 10: Diğer araçların bellek dosyaları

**Files:**
- Create: `src/fusion_cli/history/memory_files.py`
- Modify: `src/fusion_cli/engines/agent/project_instructions.py`
- Test: `tests/test_history_memory_files.py`

**Interfaces:**
- Consumes: `slug_for` (Task 2).
- Produces: `read_external_memory(home: Path, root: Path) -> str` — etiketli metin
  ya da boş dizge.

- [ ] **Step 1: Testi yaz**

`tests/test_history_memory_files.py`:

```python
"""Diğer araçların bellek dosyalarının okunması."""

from __future__ import annotations

from fusion_cli.history.memory_files import read_external_memory


def test_dosya_yoksa_bos_doner(tmp_path):
    assert read_external_memory(tmp_path, tmp_path / "proje") == ""


def test_claude_bellegi_okunur(tmp_path):
    proje = tmp_path / "proje"
    slug = str(proje).replace("/", "-")
    hedef = tmp_path / ".claude" / "projects" / slug / "memory"
    hedef.mkdir(parents=True)
    (hedef / "MEMORY.md").write_text("- kullanıcı Türkçe konuşur", encoding="utf-8")

    cikti = read_external_memory(tmp_path, proje)

    assert "kullanıcı Türkçe konuşur" in cikti
    assert "claude" in cikti


def test_hermes_bellegi_okunur(tmp_path):
    hedef = tmp_path / ".hermes" / "memories"
    hedef.mkdir(parents=True)
    (hedef / "USER.md").write_text("- kullanıcı motosiklet satıyor", encoding="utf-8")

    cikti = read_external_memory(tmp_path, tmp_path / "proje")

    assert "motosiklet" in cikti


def test_uzun_dosya_kirpilir(tmp_path):
    hedef = tmp_path / ".hermes" / "memories"
    hedef.mkdir(parents=True)
    (hedef / "MEMORY.md").write_text("x" * 20_000, encoding="utf-8")

    cikti = read_external_memory(tmp_path, tmp_path / "proje")

    assert "kırpıldı" in cikti


def test_bos_dosya_atlanir(tmp_path):
    hedef = tmp_path / ".hermes" / "memories"
    hedef.mkdir(parents=True)
    (hedef / "MEMORY.md").write_text("   \n", encoding="utf-8")

    assert read_external_memory(tmp_path, tmp_path / "proje") == ""
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_memory_files.py`
Beklenen: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.history.memory_files'`

- [ ] **Step 3: Uygulamayı yaz**

`src/fusion_cli/history/memory_files.py`:

```python
"""Diğer araçların bellek dosyalarını sistem promptuna hazırlar.

`project_instructions.py` hedef projenin KENDİ talimat dosyasını okuyor. Bu modül
onun eşleniğidir: kullanıcının başka araçlarda biriktirdiği KALICI belleği okur.
Aynı "sığ tarama" ilkesi geçerlidir — dosya varsa okunur, yoksa sessizce atlanır.
"""

from __future__ import annotations

from pathlib import Path

from .claude_source import slug_for

#: Tek bir bellek dosyasından okunacak en fazla karakter.
MAX_CHARS = 6_000


def _candidates(home: Path, root: Path) -> tuple[tuple[Path, str], ...]:
    return (
        (home / ".claude" / "projects" / slug_for(root) / "memory" / "MEMORY.md", "claude"),
        (home / ".hermes" / "memories" / "MEMORY.md", "hermes"),
        (home / ".hermes" / "memories" / "USER.md", "hermes"),
    )


def read_external_memory(home: Path, root: Path) -> str:
    """Bulunan bellek dosyalarını tek bir etiketli blok olarak döndür."""
    blocks: list[str] = []
    for path, source in _candidates(home, root):
        try:
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not content:
            continue
        trimmed = len(content) > MAX_CHARS
        if trimmed:
            content = content[:MAX_CHARS]
        suffix = "\n[…kırpıldı…]" if trimmed else ""
        blocks.append(
            f'<dis_bellek kaynak="{source}" dosya="{path.name}">\n{content}{suffix}\n</dis_bellek>'
        )
    return "\n".join(blocks)
```

`src/fusion_cli/engines/agent/project_instructions.py` sonuna:

```python
def read_all_instructions(root: Path, home: Path) -> str:
    """Proje talimatı ve dış araç belleklerini birlikte döndür.

    Sıra bilinçlidir: proje talimatı önce gelir, çünkü çakışma halinde projenin
    kendi kuralı kullanıcının genel belleğini yener.
    """
    from ...history.memory_files import read_external_memory

    parts = [read_project_instructions(root), read_external_memory(home, root)]
    return "\n".join(part for part in parts if part)
```

- [ ] **Step 4: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_history_memory_files.py`
Beklenen: 5 passed

- [ ] **Step 5: Tam paket ve kalite kapısı**

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format src/fusion_cli/history src/fusion_cli/engines/agent/project_instructions.py \
  tests/test_history_memory_files.py
.venv/bin/mypy src
.venv/bin/python -m pytest -q
```
Beklenen: hepsi temiz.

- [ ] **Step 6: Commit**

```bash
git add src/fusion_cli/history/memory_files.py \
  src/fusion_cli/engines/agent/project_instructions.py tests/test_history_memory_files.py
git commit -m "feat(agent): diğer araçların bellek dosyalarını sistem promptuna al"
```

---

## Öz Denetim

**Spec kapsamı.** Spec'in her bölümünü bir göreve bağladım:

| Spec bölümü | Görev |
|---|---|
| Kaynak adapter'ı | 1, 2, 3, 4 |
| Kurulu araç tespiti | 5 |
| Dinamik komutlar | 7 |
| Başlık çözümü | 2 (Claude), 3 (Codex), 4 (Hermes) |
| Devralma akışı (künye + read_session) | 6, 7, 8 |
| Sırlar (say, maskeleme) | 6 |
| Bellek dosyaları | 10 |
| Açılışta liste | 9 |
| Hata durumları | 2, 3, 4 (bozuk kayıt testleri), 8 (geçersiz kimlik) |

Boşluk yok.

**Bilinen sapma.** Spec "Codex `root` ile filtrelenir" demiyor ama ima ediyordu;
uygulama `root`'u Codex'te yok sayıyor ve bunun gerekçesi kodda yazılı
(`project_roots` tablosu boş ölçüldü). Yanlış filtrelemektense hepsini göstermek
tercih edildi.

**Tip tutarlılığı.** `SessionRef` alan adları (`source`, `session_id`, `title`,
`updated_at`, `turn_count`) 1., 2., 3., 4., 5., 6. ve 9. görevlerde aynı;
`Turn` (`role`, `text`, `timestamp`) 1., 2., 3., 4., 6. ve 8. görevlerde aynı;
`build_digest(source, ref, max_lines)` 6. ve 7. görevlerde aynı imzayla çağrılıyor.

**Yer tutucu taraması.** "TBD", "sonra doldur", "uygun hata yönetimi ekle" gibi
ifade yok; kod gerektiren her adımda kod var.
