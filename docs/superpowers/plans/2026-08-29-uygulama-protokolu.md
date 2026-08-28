# Uygulama Protokolü Uygulama Planı

> **Agentic worker'lar için:** ZORUNLU ALT BECERİ: Bu planı görev görev uygulamak
> için `superpowers:subagent-driven-development` (önerilen) ya da
> `superpowers:executing-plans` kullan. Adımlar takip için checkbox (`- [ ]`)
> sözdizimi kullanır.

**Hedef:** Fusion çekirdeğini stdio üzerinden satır satır JSON ile sürülebilir
hale getirmek; masaüstü uygulaması `fusion app`'i alt süreç olarak başlatıp
konuşabilsin.

**Mimari:** Yeni `src/fusion_cli/appserver/` paketi, mevcut iki dikişe takılır:
olaylar için `EventSink`, onay/soru için `Prompter`. Motor katmanına ve terminal
arayüzüne DOKUNULMAZ. Komutlar tek tek taşınmaz; mevcut kayıt defteri köprülenir.

**Teknoloji:** Python 3.11+, yalnız stdlib (`json`, `asyncio`, `dataclasses`).
Yeni bağımlılık yok.

## Global Kısıtlar

- Docstring, yorum, log ve kullanıcıya görünen tüm metinler **Türkçe**;
  tanımlayıcılar (modül, sınıf, fonksiyon, değişken) **İngilizce** ve PEP 8
  uyumlu (RULES.md "Dil").
- Tel üzerindeki JSON anahtarları **Türkçe**'dir (`tip`, `ad`, `veri`, `id`);
  spec'te onaylanan biçim budur ve uygulama tarafı buna göre yazılacaktır.
- Modül seviyesinde iş yapılmaz; import anında dosya/ağ/süreç erişimi olmaz.
- Dosya 800 satırı, fonksiyon 50 satırı geçmez.
- Motor katmanına (`engines/`, `core/`) ve terminal arayüzüne
  (`cli/repl/`, `ui/renderer.py`) **hiçbir değişiklik yapılmaz**.
- Hiçbir mesaj süreci düşürmez: bozuk girdi atlanır, hata bildirilir, süreç yaşar.
- Sır değerleri (API anahtarı, token) hiçbir çıktı satırına yazılmaz.
- Kalite kapısı: `ruff check` + `ruff format` + `mypy src` + `pytest` dördü temiz
  olmadan commit atılmaz (CLAUDE.md).
- Commit mesajı conventional format, açıklama **Türkçe**, faz/adım numarası ve
  author/co-author bilgisi YOK.

## Dosya Yapısı

| Dosya | Sorumluluk |
|---|---|
| `src/fusion_cli/appserver/__init__.py` | Paket yüzeyi |
| `src/fusion_cli/appserver/serialize.py` | Olay nesnesi → sözlük |
| `src/fusion_cli/appserver/protocol.py` | Mesaj şekilleri, kodlama ve çözme |
| `src/fusion_cli/appserver/bridges.py` | `ProtocolSink` ve `ProtocolPrompter` |
| `src/fusion_cli/appserver/session.py` | Oturum ömrü, tur çalıştırma ve iptal |
| `src/fusion_cli/appserver/commands.py` | Komut köprüsü ve seçenek sağlama |
| `src/fusion_cli/appserver/server.py` | stdio döngüsü ve istek yönlendirme |

Değiştirilecek tek mevcut dosya: `src/fusion_cli/cli/app.py` (yeni `app` alt
komutu) ve `src/fusion_cli/ui/messages.py` (kullanıcıya görünen metinler).

---

### Task 1: Olay serileştirme

**Files:**
- Create: `src/fusion_cli/appserver/__init__.py`
- Create: `src/fusion_cli/appserver/serialize.py`
- Test: `tests/test_appserver_serialize.py`

**Interfaces:**
- Consumes: `fusion_cli.core.events` (31 olay dataclass'ı).
- Produces: `event_to_dict(event: Event) -> dict[str, object]` — `"olay"`
  anahtarında sınıf adı, kalan anahtarlarda alanlar.

Ölçüldü: 31 olay sınıfının 30'u düz JSON'a çevrilebilir alanlardan oluşuyor;
yalnız `FusionCompleted` zengin bir nesne (`FusionResult`) taşıyor.

- [ ] **Step 1: Testi yaz**

`tests/test_appserver_serialize.py`:

```python
"""Olayların tel üzerine çevrilmesi."""

from __future__ import annotations

import dataclasses
import inspect
import json

from fusion_cli.appserver.serialize import event_to_dict
from fusion_cli.core import events as E


def _event_classes():
    """Modüldeki tüm olay dataclass'ları."""
    return [
        obj
        for _, obj in inspect.getmembers(E, inspect.isclass)
        if dataclasses.is_dataclass(obj) and obj.__module__ == E.__name__ and obj is not E.Event
    ]


def test_sinif_adi_olay_alanina_yazilir():
    sonuc = event_to_dict(E.TurnFinished())

    assert sonuc["olay"] == "TurnFinished"


def test_alanlar_sozluge_acilir():
    sonuc = event_to_dict(E.TurnOutcome(status="completed", elapsed_s=1.5))

    assert sonuc["status"] == "completed"
    assert sonuc["elapsed_s"] == 1.5


def test_her_olay_sinifi_json_edilebilir():
    """Değişmez: yeni bir olay düz olmayan alan taşırsa bu test kırmızıya döner.

    Sessizce bozuk JSON üretmektense burada durmak istiyoruz; kırıldığında
    yapılacak iş, o olay için elle bir çevirici yazmaktır.
    """
    for cls in _event_classes():
        ornek = _ornek_uret(cls)
        if ornek is None:
            continue
        json.dumps(event_to_dict(ornek))  # istisna fırlatmamalı


def _ornek_uret(cls):
    """Alanları varsayılan/boş değerlerle doldurup örnek üret; kurulamıyorsa None."""
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.default is not dataclasses.MISSING or f.default_factory is not dataclasses.MISSING:
            continue
        tip = str(f.type)
        if "str" in tip:
            kwargs[f.name] = "x"
        elif "float" in tip:
            kwargs[f.name] = 0.0
        elif "int" in tip:
            kwargs[f.name] = 0
        elif "bool" in tip:
            kwargs[f.name] = False
        elif "tuple" in tip:
            kwargs[f.name] = ()
        else:
            return None
    try:
        return cls(**kwargs)
    except TypeError:
        return None
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_appserver_serialize.py`
Beklenen: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.appserver'`

- [ ] **Step 3: Uygulamayı yaz**

`src/fusion_cli/appserver/__init__.py`:

```python
"""Masaüstü uygulaması için stdio protokolü.

Uygulama `fusion app` sürecini doğurur ve satır satır JSON konuşur. Bu paket
yalnız çeviri ve taşıma yapar: motor katmanı bu protokolü hiç tanımaz, mevcut
`EventSink` ve `Prompter` dikişlerine takılır.
"""

from __future__ import annotations
```

`src/fusion_cli/appserver/serialize.py`:

```python
"""Olay nesnesini tel üzerinde taşınabilir bir sözlüğe çevirir.

Tek bir genel dönüştürücü kullanılır: sınıf adı `olay` alanına yazılır, alanlar
sözlüğe açılır. Böylece yeni bir olay tipi eklendiğinde burada iş çıkmaz.

`FusionCompleted` istisnadır: taşıdığı `FusionResult` düz alanlardan oluşmaz ve
elle çevrilir.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from ..core.events import Event, FusionCompleted


def event_to_dict(event: Event) -> dict[str, Any]:
    """Olayı `{"olay": <sınıf adı>, ...alanlar}` biçiminde sözlüğe çevir."""
    if isinstance(event, FusionCompleted):
        return {"olay": "FusionCompleted", **_result_to_dict(event)}
    payload: dict[str, Any] = {"olay": type(event).__name__}
    if dataclasses.is_dataclass(event):
        for field in dataclasses.fields(event):
            payload[field.name] = _plain(getattr(event, field.name))
    return payload


def _result_to_dict(event: FusionCompleted) -> dict[str, Any]:
    """`FusionResult`'ın uygulamanın ihtiyaç duyduğu alanları."""
    result = event.result
    return {
        "gorev": result.task,
        "gorev_tipi": result.task_type,
        "kazanan": result.winner,
        "cevap": result.final_answer,
        "kaynak": result.source.value,
        "aday_sayisi": len(result.candidates),
    }


def _plain(value: Any) -> Any:
    """Değeri JSON'a uygun hale getir; bilinmeyen tip metne düşer."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if hasattr(value, "value"):  # Enum
        return _plain(value.value)
    return str(value)
```

- [ ] **Step 4: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_appserver_serialize.py`
Beklenen: 3 passed

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format src/fusion_cli/appserver tests/test_appserver_serialize.py
.venv/bin/mypy src
.venv/bin/python -m pytest -q
git add src/fusion_cli/appserver tests/test_appserver_serialize.py
git commit -m "feat(appserver): olayları tel biçimine çevir"
```

---

### Task 2: Mesaj protokolü

**Files:**
- Create: `src/fusion_cli/appserver/protocol.py`
- Test: `tests/test_appserver_protocol.py`

**Interfaces:**
- Consumes: yok.
- Produces: `Request(id: str, name: str, data: dict[str, Any])`,
  `Reply(id: str, data: dict[str, Any])`,
  `decode(line: str) -> Request | Reply | None`,
  `encode_event(payload: dict[str, Any]) -> str`,
  `encode_result(request_id: str, data: dict[str, Any]) -> str`,
  `encode_question(question_id: str, data: dict[str, Any]) -> str`,
  `encode_error(message: str) -> str`.

- [ ] **Step 1: Testi yaz**

`tests/test_appserver_protocol.py`:

```python
"""Tel biçiminin kodlanması ve çözülmesi."""

from __future__ import annotations

import json

from fusion_cli.appserver.protocol import (
    Reply,
    Request,
    decode,
    encode_error,
    encode_event,
    encode_question,
    encode_result,
)


def test_istek_cozulur():
    satir = json.dumps({"tip": "istek", "id": "7", "ad": "tur.calistir", "veri": {"gorev": "x"}})

    sonuc = decode(satir)

    assert isinstance(sonuc, Request)
    assert sonuc.id == "7"
    assert sonuc.name == "tur.calistir"
    assert sonuc.data == {"gorev": "x"}


def test_cevap_cozulur():
    satir = json.dumps({"tip": "cevap", "id": "12", "veri": {"secim": "once"}})

    sonuc = decode(satir)

    assert isinstance(sonuc, Reply)
    assert sonuc.id == "12"
    assert sonuc.data == {"secim": "once"}


def test_bozuk_json_none_doner():
    assert decode("{bozuk") is None


def test_bilinmeyen_tip_none_doner():
    assert decode(json.dumps({"tip": "baska", "id": "1"})) is None


def test_id_olmayan_istek_none_doner():
    assert decode(json.dumps({"tip": "istek", "ad": "x"})) is None


def test_bos_satir_none_doner():
    assert decode("   ") is None


def test_olay_tek_satir_olur():
    satir = encode_event({"olay": "TurnFinished"})

    assert "\n" not in satir
    assert json.loads(satir) == {"tip": "olay", "veri": {"olay": "TurnFinished"}}


def test_sonuc_istek_kimligini_tasir():
    yuk = json.loads(encode_result("7", {"ok": True}))

    assert yuk == {"tip": "sonuc", "id": "7", "veri": {"ok": True}}


def test_soru_kimlik_tasir():
    yuk = json.loads(encode_question("12", {"tur": "onay"}))

    assert yuk == {"tip": "soru", "id": "12", "veri": {"tur": "onay"}}


def test_hata_kodlanir():
    yuk = json.loads(encode_error("bozuk satır"))

    assert yuk["tip"] == "olay"
    assert yuk["veri"]["olay"] == "ProtocolError"
    assert yuk["veri"]["mesaj"] == "bozuk satır"


def test_satir_sonlari_kacisla_tasinir():
    satir = encode_event({"olay": "X", "metin": "bir\niki"})

    assert satir.count("\n") == 0
    assert json.loads(satir)["veri"]["metin"] == "bir\niki"
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_appserver_protocol.py`
Beklenen: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.appserver.protocol'`

- [ ] **Step 3: Uygulamayı yaz**

`src/fusion_cli/appserver/protocol.py`:

```python
"""Tel biçimi: satır başına bir JSON nesnesi (JSON Lines), UTF-8.

Dört mesaj tipi vardır. `id` yalnız cevap bekleyen mesajlarda bulunur ve
eşleştirme için kullanılır:

- `istek`  (uygulama → çekirdek) bir işlem çağırır
- `cevap`  (uygulama → çekirdek) çekirdeğin sorusunu yanıtlar
- `olay`   (çekirdek → uygulama) istenmeden akan durum bildirimi
- `sonuc`  (çekirdek → uygulama) bir isteğin sonucu
- `soru`   (çekirdek → uygulama) kullanıcı kararı ister

Çerçeveleme satır sınırlıdır; gövdedeki satır sonları JSON kaçışıyla taşınır,
bu yüzden bir mesaj asla ikinci bir satıra taşmaz.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Request:
    """Uygulamanın çağırdığı işlem."""

    id: str
    name: str
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Reply:
    """Uygulamanın, çekirdeğin sorusuna verdiği yanıt."""

    id: str
    data: dict[str, Any]


def decode(line: str) -> Request | Reply | None:
    """Bir satırı mesaja çevir. Çözülemeyen satır `None` döner — süreç yaşamalı."""
    stripped = line.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    kind = payload.get("tip")
    identifier = payload.get("id")
    if not isinstance(identifier, str) or not identifier:
        return None
    data = payload.get("veri")
    data = data if isinstance(data, dict) else {}
    if kind == "istek":
        name = payload.get("ad")
        if not isinstance(name, str) or not name:
            return None
        return Request(id=identifier, name=name, data=data)
    if kind == "cevap":
        return Reply(id=identifier, data=data)
    return None


def _line(payload: dict[str, Any]) -> str:
    """Tek satırlık JSON üret; Türkçe karakterler kaçırılmaz."""
    return json.dumps(payload, ensure_ascii=False)


def encode_event(payload: dict[str, Any]) -> str:
    return _line({"tip": "olay", "veri": payload})


def encode_result(request_id: str, data: dict[str, Any]) -> str:
    return _line({"tip": "sonuc", "id": request_id, "veri": data})


def encode_question(question_id: str, data: dict[str, Any]) -> str:
    return _line({"tip": "soru", "id": question_id, "veri": data})


def encode_error(message: str) -> str:
    """Protokol düzeyi hata; isteğe bağlı değil, akışta olay olarak görünür."""
    return encode_event({"olay": "ProtocolError", "mesaj": message})
```

- [ ] **Step 4: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_appserver_protocol.py`
Beklenen: 11 passed

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format src/fusion_cli/appserver tests/test_appserver_protocol.py
.venv/bin/mypy src
.venv/bin/python -m pytest -q
git add src/fusion_cli/appserver/protocol.py tests/test_appserver_protocol.py
git commit -m "feat(appserver): tel biçimini kodla ve çöz"
```

---

### Task 3: Olay ve soru köprüleri

**Files:**
- Create: `src/fusion_cli/appserver/bridges.py`
- Test: `tests/test_appserver_bridges.py`

**Interfaces:**
- Consumes: `event_to_dict` (Task 1), `encode_event`/`encode_question` (Task 2).
- Produces:
  - `Writer = Callable[[str], None]` — satır yazan taraf.
  - `ProtocolSink(writer: Writer)` — `handle(event) -> None`, `EventSink` uygular.
  - `ProtocolPrompter(writer: Writer, pending: PendingQuestions)` —
    `confirm(request) -> ApprovalAnswer`, `ask(question, options=(), recommended=None) -> str`.
  - `PendingQuestions()` — `new_question() -> tuple[str, asyncio.Future[dict]]`,
    `resolve(question_id, data) -> bool`, `cancel_all() -> None`.

Mevcut sözleşmeler (değiştirilmez): `EventSink.handle(event) -> None` senkrondur.
`Prompter.confirm(request) -> bool | ApprovalAnswer`.
`UserAsker.ask(question, options=(), recommended=None) -> str`.
`ApprovalRequest` alanları: `tool`, `args`, `danger`, `pre_allowed`, `unattended_safe`.

- [ ] **Step 1: Testi yaz**

`tests/test_appserver_bridges.py`:

```python
"""Olay ve soru köprüleri."""

from __future__ import annotations

import asyncio
import json

from fusion_cli.appserver.bridges import PendingQuestions, ProtocolPrompter, ProtocolSink
from fusion_cli.core.events import TurnOutcome
from fusion_cli.engines.agent.approval import ApprovalAnswer, ApprovalRequest


class _Tool:
    name = "write_file"


def _request(danger=None):
    return ApprovalRequest(tool=_Tool(), args={"path": "a.txt"}, danger=danger)


def test_olay_satir_olarak_yazilir():
    satirlar: list[str] = []

    ProtocolSink(satirlar.append).handle(TurnOutcome(status="completed", elapsed_s=1.0))

    yuk = json.loads(satirlar[0])
    assert yuk["tip"] == "olay"
    assert yuk["veri"]["olay"] == "TurnOutcome"
    assert yuk["veri"]["status"] == "completed"


async def test_onay_sorusu_cevapla_eslesir():
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(prompter.confirm(_request()))
    await asyncio.sleep(0)

    soru = json.loads(satirlar[0])
    assert soru["tip"] == "soru"
    assert soru["veri"]["tur"] == "onay"
    assert pending.resolve(soru["id"], {"secim": "once"}) is True

    assert await gorev is ApprovalAnswer.ONCE


async def test_yikici_istekte_oturum_secenegi_gonderilmez():
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(prompter.confirm(_request(danger="dosya siler")))
    await asyncio.sleep(0)

    secenekler = json.loads(satirlar[0])["veri"]["secenekler"]
    assert "session" not in [s["deger"] for s in secenekler]

    pending.resolve(json.loads(satirlar[0])["id"], {"secim": "deny"})
    await gorev


async def test_soru_serbest_metin_doner():
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(prompter.ask("hangi dil?"))
    await asyncio.sleep(0)
    pending.resolve(json.loads(satirlar[0])["id"], {"metin": "python"})

    assert await gorev == "python"


async def test_cevapsiz_kapanista_onay_reddedilir():
    """Uygulama cevap vermeden kapanırsa tur güvenli biçimde bitmeli."""
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(prompter.confirm(_request()))
    await asyncio.sleep(0)
    pending.cancel_all()

    assert await gorev is ApprovalAnswer.DENY


def test_eslesmeyen_kimlik_yok_sayilir():
    assert PendingQuestions().resolve("olmayan", {"secim": "once"}) is False
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_appserver_bridges.py`
Beklenen: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.appserver.bridges'`

- [ ] **Step 3: Uygulamayı yaz**

`src/fusion_cli/appserver/bridges.py`:

```python
"""Motorun iki dikişini tele bağlar.

Motor terminali tanımaz; olayları bir `EventSink`'e yayar ve kullanıcı kararını
bir `Prompter`'dan ister. Bu modül o iki sözleşmeyi uygulayıp karşılığını tel
üzerine taşır — motor katmanına hiç dokunulmaz.

Onay ve soru, `await` ile bekleyen çağrılardır. Tel üzerinde gidiş-dönüşe
dönüşürler: `soru` mesajı yollanır ve aynı `id` ile `cevap` beklenir.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from itertools import count
from typing import Any

from ..core.events import Event
from ..engines.agent.approval import ApprovalAnswer, ApprovalRequest
from ..engines.agent.engine_tools import QuestionOption
from ..ui import messages
from .protocol import encode_event, encode_question
from .serialize import event_to_dict

#: Tek satır yazan taraf. Testte listeye, üretimde stdout'a yazar.
Writer = Callable[[str], None]


class ProtocolSink:
    """Olayları tel üzerine yazan `EventSink`."""

    def __init__(self, writer: Writer) -> None:
        self._writer = writer

    def handle(self, event: Event) -> None:
        self._writer(encode_event(event_to_dict(event)))


class PendingQuestions:
    """Cevap bekleyen soruların kimlik → gelecek eşlemesi."""

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._ids = count(1)

    def new_question(self) -> tuple[str, asyncio.Future[dict[str, Any]]]:
        """Yeni bir soru kimliği ve onun cevabını taşıyacak geleceği üret."""
        identifier = str(next(self._ids))
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[identifier] = future
        return identifier, future

    def resolve(self, question_id: str, data: dict[str, Any]) -> bool:
        """Cevabı ilgili soruya bağla. Eşleşme yoksa `False` döner."""
        future = self._pending.pop(question_id, None)
        if future is None or future.done():
            return False
        future.set_result(data)
        return True

    def cancel_all(self) -> None:
        """Bekleyen tüm soruları boş cevapla kapat (uygulama kapandı)."""
        for future in self._pending.values():
            if not future.done():
                future.set_result({})
        self._pending.clear()


class ProtocolPrompter:
    """Onay ve soruyu tel üzerinden soran taraf; `Prompter` ve `UserAsker` uygular."""

    def __init__(self, writer: Writer, pending: PendingQuestions) -> None:
        self._writer = writer
        self._pending = pending

    async def confirm(self, request: ApprovalRequest) -> ApprovalAnswer:
        options = [
            {"deger": "once", "etiket": messages.TUI_APPROVAL_ONCE},
        ]
        # Yıkıcı işlem oturum iznine dönüşemez. Kural motorda da uygulanıyor;
        # burada seçenek hiç gönderilmeyerek uygulama tarafında da görünmez.
        if request.danger is None:
            options.append({"deger": "session", "etiket": messages.TUI_APPROVAL_SESSION})
        options.append({"deger": "deny", "etiket": messages.TUI_APPROVAL_DENY})

        data = await self._ask_wire(
            {
                "tur": "onay",
                "arac": request.tool.name,
                "argumanlar": {str(k): str(v) for k, v in request.args.items()},
                "tehlike": request.danger,
                "secenekler": options,
            }
        )
        secim = data.get("secim")
        if secim == "once":
            return ApprovalAnswer.ONCE
        if secim == "session":
            return ApprovalAnswer.SESSION
        return ApprovalAnswer.DENY

    async def ask(
        self,
        question: str,
        options: tuple[QuestionOption, ...] = (),
        recommended: str | None = None,
    ) -> str:
        data = await self._ask_wire(
            {
                "tur": "soru",
                "soru": question,
                "secenekler": [
                    {"etiket": o.label, "aciklama": o.description} for o in options
                ],
                "onerilen": recommended,
            }
        )
        metin = data.get("metin")
        return metin if isinstance(metin, str) else ""

    async def _ask_wire(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Soruyu yolla ve cevabı bekle. Uygulama kapanırsa boş sözlük döner."""
        identifier, future = self._pending.new_question()
        self._writer(encode_question(identifier, payload))
        return await future
```

- [ ] **Step 4: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_appserver_bridges.py`
Beklenen: 6 passed

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format src/fusion_cli/appserver tests/test_appserver_bridges.py
.venv/bin/mypy src
.venv/bin/python -m pytest -q
git add src/fusion_cli/appserver/bridges.py tests/test_appserver_bridges.py
git commit -m "feat(appserver): olay ve soru köprülerini kur"
```

---

### Task 4: Komut köprüsü

**Files:**
- Create: `src/fusion_cli/appserver/commands.py`
- Test: `tests/test_appserver_commands.py`

**Interfaces:**
- Consumes: `fusion_cli.cli.repl.commands.build_registry`, `ReplState`.
- Produces:
  - `list_commands(registry) -> list[dict[str, str]]` — `ad`, `aciklama`, `grup`, `kullanim`.
  - `run_command(registry, state, name, argument) -> dict[str, Any]` —
    `{"ok": bool, "metin": str}`.
  - `command_choices(state, name) -> list[dict[str, str]] | None` —
    seçici açan komut için `deger`/`etiket`/`aciklama`; komut seçici açmıyorsa `None`.

Seçici açan beş komut ölçüldü: `model` (argümansız), `provider`, `development`,
`profiles edit`, `providers add`. Seçenek üreticileri depoda zaten var
(`cli/repl/model_flows.py`); protokol onları yeniden kullanır, kendi listesini
kurmaz.

- [ ] **Step 1: Testi yaz**

`tests/test_appserver_commands.py`:

```python
"""Komut köprüsü."""

from __future__ import annotations

from pathlib import Path

from fusion_cli.appserver.commands import command_choices, list_commands, run_command
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _state(tmp_path):
    return ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


def test_liste_kayit_defteriyle_ortusur():
    registry = build_registry()

    liste = list_commands(registry)

    assert len(liste) == len(registry.all())
    assert all(satir["ad"] and satir["aciklama"] for satir in liste)


def test_liste_grup_ve_kullanim_tasir():
    liste = {satir["ad"]: satir for satir in list_commands(build_registry())}

    assert liste["skills"]["grup"] == "Bilgi"
    assert liste["skills"]["kullanim"] == "[arama]"


def test_komut_calisir_ve_metin_doner(tmp_path):
    sonuc = run_command(build_registry(), _state(tmp_path), "thinking", "")

    assert sonuc["ok"] is True
    assert isinstance(sonuc["metin"], str)


def test_bilinmeyen_komut_hata_doner(tmp_path):
    sonuc = run_command(build_registry(), _state(tmp_path), "olmayan", "")

    assert sonuc["ok"] is False
    assert "olmayan" in sonuc["metin"]


def test_isleyici_istisnasi_sureci_dusurmez(tmp_path):
    """Komut işleyicisi patlarsa hata sonuç olarak dönmeli, dışarı sızmamalı."""
    registry = build_registry()
    state = _state(tmp_path)
    # `forget` argümansız çağrıldığında kullanım metni döndürür; istisna değil.
    sonuc = run_command(registry, state, "forget", "")

    assert isinstance(sonuc["ok"], bool)


def test_secici_acan_komut_secenek_dondurur(tmp_path):
    secenekler = command_choices(_state(tmp_path), "level")

    assert secenekler is not None
    assert all("deger" in s and "etiket" in s for s in secenekler)


def test_secici_acmayan_komut_none_doner(tmp_path):
    assert command_choices(_state(tmp_path), "thinking") is None
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_appserver_commands.py`
Beklenen: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.appserver.commands'`

- [ ] **Step 3: Uygulamayı yaz**

`src/fusion_cli/appserver/commands.py`:

```python
"""Slash komut defterini tele köprüler.

Elli komut tek tek taşınmaz: mevcut kayıt defteri olduğu gibi açılır. Komut
işleyicileri zaten saf ve senkrondur (`(state, argüman) -> str`), bu yüzden
köprü incedir. Yeni bir komut eklendiğinde uygulamada kendiliğinden belirir ve
iki yüzey ayrışmaz.

Terminalde seçici açan komutlar protokolde seçici açmaz: `command_choices`
seçenek listesini döndürür, uygulama kendi arayüzünde gösterir ve seçimi
argüman olarak geri gönderir.
"""

from __future__ import annotations

from typing import Any

from ..cli.repl import model_flows
from ..cli.repl.commands import CommandRegistry
from ..cli.repl.state import ReplState
from ..ui import messages


def list_commands(registry: CommandRegistry) -> list[dict[str, str]]:
    """Kayıt defterindeki tüm komutlar; uygulamanın menü kurabileceği biçimde."""
    return [
        {
            "ad": command.name,
            "aciklama": command.summary,
            "grup": command.group,
            "kullanim": command.usage,
        }
        for command in registry.all()
    ]


def run_command(
    registry: CommandRegistry, state: ReplState, name: str, argument: str
) -> dict[str, Any]:
    """Komutu çalıştır ve sonucunu döndür. İstisna sızdırmaz."""
    command = registry.get(name)
    if command is None:
        return {"ok": False, "metin": messages.REPL_UNKNOWN_COMMAND.format(name=name)}
    try:
        return {"ok": True, "metin": command.handler(state, argument)}
    except Exception as error:  # araç sınırı: hata sonuca çevrilir, süreç yaşar
        return {"ok": False, "metin": str(error)}


#: Terminalde seçici açan komutlar → seçenek üreticileri. Üreticiler depoda
#: zaten var; protokol kendi listesini kurmaz, aynı kaynağı kullanır.
_CHOICE_BUILDERS = {
    "level": lambda state: model_flows.level_choices(state.config),
    "mode": lambda state: model_flows.mode_choices(state.config),
    "effort": lambda state: model_flows.effort_choices(),
}


def command_choices(state: ReplState, name: str) -> list[dict[str, str]] | None:
    """Seçici açan komut için seçenekler; komut seçici açmıyorsa `None`."""
    builder = _CHOICE_BUILDERS.get(name)
    if builder is None:
        return None
    return [
        {"deger": choice.value, "etiket": choice.label, "aciklama": choice.description}
        for choice in builder(state)
    ]
```

**Not:** `messages.REPL_UNKNOWN_COMMAND` sabiti `ui/messages.py`'de ZATEN VAR
(doğrulandı). Yeniden tanımlama; olduğu gibi kullan.

- [ ] **Step 4: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_appserver_commands.py`
Beklenen: 7 passed

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format src/fusion_cli/appserver tests/test_appserver_commands.py
.venv/bin/mypy src
.venv/bin/python -m pytest -q
git add src/fusion_cli/appserver/commands.py src/fusion_cli/ui/messages.py \
  tests/test_appserver_commands.py
git commit -m "feat(appserver): slash komut defterini tele köprüle"
```

---

### Task 5: Oturum ve istek yönlendirme

**Files:**
- Create: `src/fusion_cli/appserver/session.py`
- Test: `tests/test_appserver_session.py`

**Interfaces:**
- Consumes: Task 1-4'ün tamamı; `fusion_cli.cli.session.run_agent_task`.
- Produces: `AppSession(writer: Writer, *, root: Path, home: Path)` —
  `async handle(request: Request) -> None`, `resolve_reply(reply: Reply) -> bool`,
  `async close() -> None`.

`run_agent_task` imzası (değiştirilmez): `task`, `config`, `sinks`,
`prompter_factory`, `mode`, `root`, `home`, `history`, `interactive`.

- [ ] **Step 1: Testi yaz**

`tests/test_appserver_session.py`:

```python
"""Oturum ömrü ve istek yönlendirme."""

from __future__ import annotations

import asyncio
import json

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession


def _session(tmp_path, satirlar):
    return AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")


async def test_bilinmeyen_istek_hata_sonucu_doner(tmp_path):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    await oturum.handle(Request(id="1", name="olmayan.istek", data={}))

    sonuc = json.loads(satirlar[-1])
    assert sonuc["tip"] == "sonuc"
    assert sonuc["id"] == "1"
    assert sonuc["veri"]["ok"] is False


async def test_durum_istegi_kok_dizini_bildirir(tmp_path):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    await oturum.handle(Request(id="2", name="oturum.durum", data={}))

    veri = json.loads(satirlar[-1])["veri"]
    assert veri["ok"] is True
    assert veri["kok"] == str(tmp_path)


async def test_komut_listesi_doner(tmp_path):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    await oturum.handle(Request(id="3", name="komut.listele", data={}))

    veri = json.loads(satirlar[-1])["veri"]
    assert veri["ok"] is True
    assert any(k["ad"] == "help" for k in veri["komutlar"])


async def test_eslesmeyen_cevap_false_doner(tmp_path):
    from fusion_cli.appserver.protocol import Reply

    oturum = _session(tmp_path, [])

    assert oturum.resolve_reply(Reply(id="yok", data={})) is False


async def test_kapanista_bekleyen_sorular_serbest_birakilir(tmp_path):
    """Kapanış bekleyen soruyu sonsuza dek asılı bırakmamalı."""
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    kimlik, gelecek = oturum.pending.new_question()

    await oturum.close()
    await asyncio.sleep(0)

    assert gelecek.done()
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_appserver_session.py`
Beklenen: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.appserver.session'`

- [ ] **Step 3: Uygulamayı yaz**

`src/fusion_cli/appserver/session.py`:

```python
"""Oturum ömrü: istekleri karşılar, turu çalıştırır, kapanışı düzenler.

Bir süreç BİR oturum yürütür. Uygulama ikinci bir sohbet istiyorsa ikinci bir
süreç başlatır; böylece paylaşılan durum, kilit ve sahiplik sorunları hiç
doğmaz ve bir oturumun çökmesi diğerini etkilemez.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..cli.repl.commands import build_registry
from ..cli.repl.state import ReplState
from ..config.loader import load_config
from ..engines.agent.approval import ApprovalMode
from ..memory.factory import null_memory
from ..ui import messages
from .bridges import PendingQuestions, ProtocolPrompter, ProtocolSink, Writer
from .commands import command_choices, list_commands, run_command
from .protocol import Reply, Request, encode_result


class AppSession:
    """Uygulamanın sürdüğü tek oturum."""

    def __init__(self, writer: Writer, *, root: Path, home: Path) -> None:
        self._writer = writer
        self._root = root
        self._home = home
        self._config = load_config()
        self._mode = ApprovalMode.AUTO
        self.pending = PendingQuestions()
        self._registry = build_registry(home)
        self._state = ReplState(
            config=self._config, memory=null_memory(), root=root, home=home
        )
        self._turn: asyncio.Task[Any] | None = None

    async def handle(self, request: Request) -> None:
        """İsteği çalıştır ve sonucunu yaz. İstisna sızdırmaz."""
        try:
            data = await self._dispatch(request)
        except Exception as error:  # istek sınırı: süreç çökmemeli
            data = {"ok": False, "metin": str(error)}
        self._writer(encode_result(request.id, data))

    async def _dispatch(self, request: Request) -> dict[str, Any]:
        if request.name == "oturum.durum":
            return {
                "ok": True,
                "kok": str(self._root),
                "model": self._config.agent.model,
                "mod": self._mode.value,
            }
        if request.name == "komut.listele":
            return {"ok": True, "komutlar": list_commands(self._registry)}
        if request.name == "komut.calistir":
            name = str(request.data.get("ad", ""))
            argument = str(request.data.get("arguman", ""))
            return run_command(self._registry, self._state, name, argument)
        if request.name == "komut.secenekler":
            name = str(request.data.get("ad", ""))
            choices = command_choices(self._state, name)
            return {"ok": choices is not None, "secenekler": choices or []}
        if request.name == "tur.calistir":
            return await self._run_turn(str(request.data.get("gorev", "")))
        if request.name == "tur.kes":
            return self._cancel_turn()
        return {"ok": False, "metin": messages.APP_UNKNOWN_REQUEST.format(name=request.name)}

    async def _run_turn(self, task: str) -> dict[str, Any]:
        """Görevi agent motoruyla çalıştır; olaylar tel üzerinden akar."""
        if not task.strip():
            return {"ok": False, "metin": messages.RUN_EMPTY_TASK}
        from ..cli.session import run_agent_task

        sink = ProtocolSink(self._writer)
        prompter = ProtocolPrompter(self._writer, self.pending)
        self._turn = asyncio.ensure_future(
            run_agent_task(
                task,
                self._config,
                sinks=(sink,),
                prompter_factory=lambda _drain: prompter,
                mode=self._mode,
                root=self._root,
                home=self._home,
                interactive=True,
            )
        )
        try:
            outcome = await self._turn
        except asyncio.CancelledError:
            return {"ok": False, "metin": messages.APP_TURN_CANCELLED}
        finally:
            self._turn = None
        return {"ok": outcome.ok, "metin": outcome.final_text}

    def _cancel_turn(self) -> dict[str, Any]:
        if self._turn is None or self._turn.done():
            return {"ok": False, "metin": messages.APP_NO_RUNNING_TURN}
        self._turn.cancel()
        return {"ok": True, "metin": messages.APP_TURN_CANCELLED}

    def resolve_reply(self, reply: Reply) -> bool:
        """Uygulamanın cevabını bekleyen soruya bağla."""
        return self.pending.resolve(reply.id, reply.data)

    async def close(self) -> None:
        """Çalışan turu iptal et, bekleyen soruları serbest bırak."""
        if self._turn is not None and not self._turn.done():
            self._turn.cancel()
        self.pending.cancel_all()
```

`ui/messages.py`'ye ekle:

```python
#: Uygulama protokolü metinleri.
APP_UNKNOWN_REQUEST = "Bilinmeyen istek: {name}"
APP_TURN_CANCELLED = "Tur iptal edildi."
APP_NO_RUNNING_TURN = "Çalışan tur yok."
```

- [ ] **Step 4: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_appserver_session.py`
Beklenen: 5 passed

- [ ] **Step 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format src/fusion_cli/appserver src/fusion_cli/ui/messages.py \
  tests/test_appserver_session.py
.venv/bin/mypy src
.venv/bin/python -m pytest -q
git add src/fusion_cli/appserver/session.py src/fusion_cli/ui/messages.py \
  tests/test_appserver_session.py
git commit -m "feat(appserver): oturumu kur ve istekleri yönlendir"
```

---

### Task 6: stdio sunucusu ve `fusion app` komutu

**Files:**
- Create: `src/fusion_cli/appserver/server.py`
- Modify: `src/fusion_cli/cli/app.py` (yeni `app` alt komutu)
- Test: `tests/test_appserver_server.py`

**Interfaces:**
- Consumes: Task 1-5'in tamamı.
- Produces: `async serve(reader, writer_line, *, root, home) -> None` —
  satır kaynağını okur, oturumu sürer, akış bitince düzgün kapanır.

- [ ] **Step 1: Testi yaz**

`tests/test_appserver_server.py`:

```python
"""stdio döngüsü: satır girdi → satır çıktı."""

from __future__ import annotations

import json

from fusion_cli.appserver.server import serve


async def _run(satirlar_girdi, tmp_path):
    cikti: list[str] = []

    async def _reader():
        for satir in satirlar_girdi:
            yield satir

    await serve(_reader(), cikti.append, root=tmp_path, home=tmp_path / "ev")
    return cikti


async def test_istek_sonuc_uretir(tmp_path):
    girdi = [json.dumps({"tip": "istek", "id": "1", "ad": "oturum.durum", "veri": {}})]

    cikti = await _run(girdi, tmp_path)

    sonuc = json.loads(cikti[-1])
    assert sonuc["tip"] == "sonuc" and sonuc["id"] == "1"


async def test_bozuk_satir_sureci_dusurmez(tmp_path):
    girdi = [
        "{bozuk json",
        json.dumps({"tip": "istek", "id": "2", "ad": "oturum.durum", "veri": {}}),
    ]

    cikti = await _run(girdi, tmp_path)

    hatalar = [json.loads(s) for s in cikti if json.loads(s).get("tip") == "olay"]
    assert any(h["veri"]["olay"] == "ProtocolError" for h in hatalar)
    assert any(json.loads(s).get("id") == "2" for s in cikti)


async def test_eslesmeyen_cevap_hata_olayi_uretir(tmp_path):
    girdi = [json.dumps({"tip": "cevap", "id": "yok", "veri": {}})]

    cikti = await _run(girdi, tmp_path)

    assert any(json.loads(s)["veri"].get("olay") == "ProtocolError" for s in cikti)


async def test_akis_bitince_duzgun_kapanir(tmp_path):
    """stdin kapanınca döngü biter; istisna fırlamaz."""
    cikti = await _run([], tmp_path)

    assert cikti == []
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_appserver_server.py`
Beklenen: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.appserver.server'`

- [ ] **Step 3: Uygulamayı yaz**

`src/fusion_cli/appserver/server.py`:

```python
"""stdio döngüsü: satır oku, yönlendir, satır yaz.

Süreç yalnız akış bitince (uygulama stdin'i kapatınca) ya da açıkça
sonlandırılınca durur. Hiçbir bozuk mesaj süreci düşürmez.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from pathlib import Path

from .bridges import Writer
from .protocol import Reply, Request, decode, encode_error
from .session import AppSession


async def serve(
    lines: AsyncIterator[str], writer: Writer, *, root: Path, home: Path
) -> None:
    """Satır akışını oturuma bağla ve akış bitene kadar sür."""
    session = AppSession(writer, root=root, home=home)
    try:
        async for line in lines:
            message = decode(line)
            if message is None:
                writer(encode_error("çözülemeyen satır"))
                continue
            if isinstance(message, Request):
                await session.handle(message)
                continue
            if isinstance(message, Reply) and not session.resolve_reply(message):
                writer(encode_error("eşleşmeyen cevap kimliği"))
    finally:
        await session.close()


async def _stdin_lines() -> AsyncIterator[str]:
    """stdin'i bloklamadan satır satır oku."""
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            return
        yield line


def _stdout_writer(line: str) -> None:
    """Tek satır yaz ve hemen boşalt; uygulama olayları anında görmeli."""
    try:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
    except (BrokenPipeError, ValueError):
        # Yazılamayan bir kanala olay biriktirmek bellek sızdırır; sessizce dur.
        raise SystemExit(0) from None


async def run_stdio(root: Path, home: Path) -> None:
    """Gerçek stdio üzerinde protokolü çalıştır."""
    await serve(_stdin_lines(), _stdout_writer, root=root, home=home)
```

`src/fusion_cli/cli/app.py` — `mcp` komutunun hemen ardına ekle:

```python
@app.command()
def app_protocol() -> None:
    """Masaüstü uygulaması için stdio protokolünü konuş.

    Uygulama bu süreci kendisi doğurur ve stdin/stdout üzerinden satır satır
    JSON konuşur. Doğrudan elle çalıştırmak için değildir.
    """
    import asyncio
    from pathlib import Path

    from ..appserver.server import run_stdio

    asyncio.run(run_stdio(Path.cwd(), Path.home()))
```

**Not:** Typer komut adını fonksiyon adından türetir ve alt çizgiyi tireye
çevirir; bu tanım `fusion app-protocol` üretir. Spec `fusion app` diyor, bu
yüzden dekoratöre açık ad verilmelidir:

```python
@app.command(name="app")
def app_protocol() -> None:
```

- [ ] **Step 4: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_appserver_server.py`
Beklenen: 4 passed

- [ ] **Step 5: Gerçek süreçle duman testi**

```bash
printf '%s\n' '{"tip":"istek","id":"1","ad":"oturum.durum","veri":{}}' \
  | .venv/bin/fusion app
```
Beklenen: tek satırlık bir `sonuc` mesajı; süreç girdi bitince kendiliğinden
kapanır ve hata basmaz.

- [ ] **Step 6: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format src/fusion_cli/appserver src/fusion_cli/cli/app.py \
  tests/test_appserver_server.py
.venv/bin/mypy src
.venv/bin/python -m pytest -q
git add src/fusion_cli/appserver/server.py src/fusion_cli/cli/app.py \
  tests/test_appserver_server.py
git commit -m "feat(cli): uygulama protokolünü stdio üzerinden aç"
```

---

### Task 7: Sır sızıntısı değişmezi

**Files:**
- Test: `tests/test_appserver_secrets.py`

**Interfaces:**
- Consumes: Task 1-6'nın tamamı.
- Produces: yeni üretim kodu yok; yalnız bir değişmez.

Spec'in kuralı: sır değerleri hiçbir çıktı satırına yazılmaz. Bu görev o kuralı
teste bağlar; kural bir gün ihlal edilirse test kırmızıya döner.

- [ ] **Step 1: Testi yaz**

`tests/test_appserver_secrets.py`:

```python
"""Sır değerleri tel üzerine sızmamalı."""

from __future__ import annotations

import json

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession

GIZLI = "sk-test-0123456789abcdefghijklmnop"


async def test_komut_argumani_sonuc_metnine_yansimaz(tmp_path):
    """Anahtar argüman olarak geçse bile sonuç satırında görünmemeli."""
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    await oturum.handle(
        Request(id="1", name="komut.calistir", data={"ad": "learn", "arguman": GIZLI})
    )

    assert all(GIZLI not in satir for satir in satirlar), "sır çıktı satırına sızdı"


async def test_bilinmeyen_istek_verisi_geri_yankilanmaz(tmp_path):
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    await oturum.handle(Request(id="2", name="olmayan", data={"token": GIZLI}))

    assert all(GIZLI not in satir for satir in satirlar)
```

- [ ] **Step 2: Testi çalıştır ve sonucu DEĞERLENDİR**

Çalıştır: `.venv/bin/python -m pytest -q tests/test_appserver_secrets.py`

Bu test kırmızı da yeşil de olabilir; ikisi de bilgi taşır:

- **Yeşil ise** kural zaten tutuyor demektir. Üretim kodunu DEĞİŞTİRME; testi
  değişmez olarak bırak ve commit et.
- **Kırmızı ise** gerçek bir sızıntı bulmuşsun demektir. Sızdıran yolu bul ve
  yalnız o yolu düzelt: sonuç metnine argümanı yankılayan yeri maskele. Kapsamı
  genişletme.

- [ ] **Step 3: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format tests/test_appserver_secrets.py
.venv/bin/mypy src
.venv/bin/python -m pytest -q
git add tests/test_appserver_secrets.py
git commit -m "test(appserver): sırların tele sızmadığını sabitle"
```

---

## Öz Denetim

**Spec kapsamı.** Spec'in her bölümünü bir göreve bağladım:

| Spec bölümü | Görev |
|---|---|
| Olay serileştirme + değişmez test | 1 |
| Mesaj tipleri, çerçeveleme, bozuk satır | 2 |
| Onay/soru gidiş-dönüşü, cevapsız kapanış | 3 |
| Yıkıcı işlemde oturum izninin gönderilmemesi | 3 |
| Komut köprüsü, seçenek sağlama | 4 |
| Oturum ömrü, `tur.calistir`, `tur.kes`, istekler | 5 |
| stdio döngüsü, `fusion app`, düzgün kapanış | 6 |
| Sır kuralı | 7 |
| Config yarışı | kapsam dışı (spec'te bilinen risk) |

Boşluk yok.

**Tip tutarlılığı.** `Writer` (Task 3) 5. ve 6. görevlerde aynı imzayla kullanılıyor.
`Request`/`Reply` (Task 2) 5. ve 6. görevlerde aynı alan adlarıyla geçiyor
(`id`, `name`, `data`). `PendingQuestions.resolve` 3., 5. ve 6. görevlerde
`bool` döndürüyor. `event_to_dict` (Task 1) yalnız 3. görevde çağrılıyor.

**Yer tutucu taraması.** "TBD", "sonra doldur", "uygun hata yönetimi ekle" gibi
ifade yok; kod gerektiren her adımda kod var. Task 7 bilinçli olarak iki sonuçlu
bir denetimdir ve her iki dal için de ne yapılacağı açıkça yazılmıştır.

**Bilinen belirsizlik.** Task 4'teki `_CHOICE_BUILDERS` yalnız üç komutu kapsıyor
(`level`, `mode`, `effort`) çünkü depoda hazır seçenek üreticisi olan komutlar
bunlar. `provider`, `development` ve `profiles edit` gizli anahtar istemi ya da
iki adımlı akış gerektiriyor; bunlar protokolde ayrı bir tasarım ister ve bu
plana dahil değildir. Uygulama o komutları çağırdığında `komut.secenekler`
`ok:false` döner ve uygulama bunu "bu komut şimdilik uygulamada yok" diye
gösterir.
