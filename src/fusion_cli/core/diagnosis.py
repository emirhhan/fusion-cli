"""Ham hata çıktısını yapılandırılmış tanıya çevirir.

SWE-Doctor'ın bulgusu: testi çalıştırıp çıktıyı modele vermek yetmiyor; kazanç
çıktının "şüpheli konum + belirti" olarak yapılandırılmasından geliyor. Ölçüldü
(5 Eylül Godot koşusu): `SCRIPT ERROR: Parse Error ... at: GDScript::reload
(res://player.gd:12)` satırı elimizdeydi ve kurtarma turu bunu dosya/satır/belirti
hâline getiremediği için model aynı yanlışı tekrarladı.

Tanı UYDURULMAZ: desen eşleşmezse `None` döner ve ham çıktı olduğu gibi kullanılır.
Yanlış bir tanı, tanı olmamasından kötüdür — modeli doğru koda müdahale ettirir.

`core` katmanındadır ve saftır: dosya, ağ, süreç bilmez.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Godot: `at: GDScript::reload (res://player.gd:12)`
_GODOT_KONUM = re.compile(r"at:.*?\((?P<path>res://[^\s:()]+):(?P<line>\d+)\)")
_GODOT_BELIRTI = re.compile(r"^(?:SCRIPT )?ERROR:\s*(?P<msg>.+)$", re.MULTILINE)

#: Python traceback çerçevesi: `File "/proje/x.py", line 4, in f`
_PY_CERCEVE = re.compile(r'  File "(?P<path>[^"]+)", line (?P<line>\d+)(?:, in .+)?')
_PY_TRACE_HEADER = "Traceback (most recent call last):"
_PY_GROUP_HEADER = "Exception Group Traceback (most recent call last):"
_PY_TRACE_BELIRTI = re.compile(
    r"(?P<msg>(?:[A-Za-z_][\w.]*?(?:Error|Exception|Warning)|Error|Exception|Warning|"
    r"KeyboardInterrupt|SystemExit|GeneratorExit|StopIteration|StopAsyncIteration)"
    r"(?::[ \t]?.*)?)"
)
#: Traceback'in son satırı: `KeyError: 'port'`
_PY_BELIRTI = re.compile(r"^(?P<msg>[A-Za-z_][\w.]*(?:Error|Exception|Warning)\b.*)$", re.MULTILINE)

#: pytest özeti: `tests/test_x.py:5: AssertionError`
_PYTEST_KONUM = re.compile(r"^(?P<path>[^\s:]+\.py):(?P<line>\d+): (?P<msg>.+)$", re.MULTILINE)
#: pytest kısa özeti: `FAILED tests/test_x.py::test_y - assert 2.0 == 4.0`
_PYTEST_OZET = re.compile(r"^FAILED (?P<test>\S+) - (?P<msg>.+)$", re.MULTILINE)

#: node/tsc: `/proje/app.js:12` ardından `SyntaxError: ...`
#: Satır YALNIZ `yol:satır` olmalı: `grep -n` (`a.js:12:metin`) ya da derleyici/linter
#: (`a.ts:12:5 - error`) çıktısı çalışma zamanı hatası tanısı üretmesin. Ölçüldü (30 Ekim).
_NODE_KONUM = re.compile(
    r"^(?P<path>[^\s:]+\.(?:js|mjs|cjs|ts|tsx)):(?P<line>\d+)[ \t]*$", re.MULTILINE
)


@dataclass(frozen=True, slots=True)
class Diagnosis:
    """Bir hatanın konumu ve belirtisi — kurtarma turunun görevi budur."""

    path: str
    line: int
    symptom: str
    #: Tanının çıkarıldığı ham satır; model şüphelenirse asla kaybolmaz.
    quote: str = ""

    def as_guidance(self) -> str:
        """Kurtarma turuna verilecek tek satırlık yönerge."""
        return (
            f"Hata {self.path}:{self.line} konumunda: {self.symptom}. "
            "Bu konumu ve ilgili çağrı zincirini incele."
        )


def diagnose(output: str) -> Diagnosis | None:
    """Çıktıyı tanıya çevir; desen eşleşmezse `None`."""
    for cozumleyici in (_godot, _python_traceback, _pytest, _node):
        tani = cozumleyici(output)
        if tani is not None:
            return tani
    return None


def _godot(output: str) -> Diagnosis | None:
    konum = _GODOT_KONUM.search(output)
    if konum is None:
        return None
    belirti = _GODOT_BELIRTI.search(output)
    return Diagnosis(
        path=konum.group("path"),
        line=int(konum.group("line")),
        symptom=belirti.group("msg").strip() if belirti else "motor hata bildirdi",
        quote=konum.group(0),
    )


def _python_traceback(output: str) -> Diagnosis | None:
    # A frame and terminal exception must belong to the same complete plain block.
    # Group rendering has multiple branches: do not flatten it into a guessed cause.
    latest = None
    active = False
    frame = None
    for raw_line in output.splitlines():
        line = raw_line.rstrip(" \t")
        if line == _PY_TRACE_HEADER:
            active = True
            frame = None
            continue
        if line.lstrip(" \t+|") in {_PY_TRACE_HEADER, _PY_GROUP_HEADER}:
            active = False
            frame = None
            continue
        if not active:
            continue
        candidate = _PY_CERCEVE.fullmatch(line)
        if candidate is not None:
            frame = candidate
            continue
        if line.startswith("  File "):
            # An unreadable inner frame cannot make the last outer frame definitive.
            active = False
            frame = None
            continue
        symptom = _PY_TRACE_BELIRTI.fullmatch(line)
        if symptom is not None:
            if frame is not None:
                path, number = frame.group("path", "line")
                latest = Diagnosis(
                    path=path,
                    line=int(number),
                    symptom=symptom.group("msg").strip(),
                    quote=f'File "{path}", line {number}',
                )
            active = False
            frame = None
        elif line and not line[0].isspace():
            active = False
            frame = None
    return latest


def _pytest(output: str) -> Diagnosis | None:
    konum = None
    for eslesme in _PYTEST_KONUM.finditer(output):
        konum = eslesme
    if konum is None:
        return None
    ozet = _PYTEST_OZET.search(output)
    return Diagnosis(
        path=konum.group("path"),
        line=int(konum.group("line")),
        symptom=(ozet.group("msg") if ozet else konum.group("msg")).strip(),
        quote=konum.group(0),
    )


def _node(output: str) -> Diagnosis | None:
    konum = _NODE_KONUM.search(output)
    if konum is None:
        return None
    belirti = _PY_BELIRTI.search(output)
    if belirti is None:
        # Hata satırı olmayan "yol:satır" tanı değildir: yanlış tanı, tanı olmamasından kötüdür.
        return None
    return Diagnosis(
        path=konum.group("path"),
        line=int(konum.group("line")),
        symptom=belirti.group("msg").strip(),
        quote=konum.group(0),
    )
