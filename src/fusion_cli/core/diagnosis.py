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
_PY_CERCEVE = re.compile(r'File "(?P<path>[^"]+)", line (?P<line>\d+)')
#: Traceback'in son satırı: `KeyError: 'port'`
_PY_BELIRTI = re.compile(r"^(?P<msg>[A-Za-z_][\w.]*(?:Error|Exception|Warning)\b.*)$", re.MULTILINE)

#: pytest özeti: `tests/test_x.py:5: AssertionError`
_PYTEST_KONUM = re.compile(r"^(?P<path>[^\s:]+\.py):(?P<line>\d+): (?P<msg>.+)$", re.MULTILINE)
#: pytest kısa özeti: `FAILED tests/test_x.py::test_y - assert 2.0 == 4.0`
_PYTEST_OZET = re.compile(r"^FAILED (?P<test>\S+) - (?P<msg>.+)$", re.MULTILINE)

#: node/tsc: `/proje/app.js:12` ardından `SyntaxError: ...`
_NODE_KONUM = re.compile(r"^(?P<path>[^\s:]+\.(?:js|mjs|cjs|ts|tsx)):(?P<line>\d+)", re.MULTILINE)


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
        return f"Hata {self.path}:{self.line} konumunda: {self.symptom}. Kök nedeni orada ara."


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
    if "Traceback (most recent call last)" not in output:
        return None
    cerceveler = _PY_CERCEVE.findall(output)
    if not cerceveler:
        return None
    # EN İÇTEKİ çerçeve seçilir: kök neden en dıştaki çağrı değil, hatanın
    # gerçekleştiği yerdir. Dıştaki çerçeveyi göstermek modeli yanlış dosyaya yollar.
    path, line = cerceveler[-1]
    belirtiler = _PY_BELIRTI.findall(output)
    return Diagnosis(
        path=path,
        line=int(line),
        symptom=belirtiler[-1].strip() if belirtiler else "istisna",
        quote=f'File "{path}", line {line}',
    )


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
    return Diagnosis(
        path=konum.group("path"),
        line=int(konum.group("line")),
        symptom=belirti.group("msg").strip() if belirti else "çalışma zamanı hatası",
        quote=konum.group(0),
    )
