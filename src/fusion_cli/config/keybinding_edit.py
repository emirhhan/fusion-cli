"""`keybindings.json` düzenleme: bir eylemi tuşa bağla, bağı kaldır, varsayılana dön (P-046).

Masaüstü Ayarlar › Kısayollar bu işlemleri `kisayol.*` istekleriyle yapar; dosya elle de
düzenlenebilir ve iki yol aynı biçimi üretir. Dosyada yalnız varsayılandan FARKLAR durur:
`"mod+j": null` varsayılan bağı kaldırır, `"mod+t": "terminal"` yeni bağ ekler. Diğer
bağlamlar (terminal tarafı) ve okunamayan girdiler olduğu gibi korunur.

Bozuk dosyanın üstüne yazılmaz: kullanıcının elle yazdığı içerik kaybolmasın diye işlem
reddedilir ve dosyanın düzeltilmesi istenir.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..core.atomic_file import atomic_replace_text
from ..core.errors import ConfigError
from .keybindings import default_keymap, is_valid_action, load_keymap, normalize_key

#: Bağlam tablosu; okunamayan değerler de korunduğu için değer tipi geniştir.
Table = dict[str, object]


@dataclass(frozen=True, slots=True)
class KeyEditResult:
    """Düzenleme sonucu: başarısızlıkta `problem` ya da çakışan eylem (`conflict`) ve tuşu dolu."""

    ok: bool
    problem: str | None = None
    conflict: str | None = None
    key: str | None = None


def bind_action(path: Path, context: str, action: str, key: str, *, force: bool) -> KeyEditResult:
    """`action` eylemini YALNIZ `key` tuşuna bağla (eylemin önceki tuşları kalkar).

    Tuş başka bir eyleme bağlıysa `force` olmadan çakışma döner; `force` ile o eylem bu
    tuşu kaybeder.
    """
    canonical, problem = normalize_key(context, key)
    if canonical is None:
        return KeyEditResult(False, problem=problem)
    if not is_valid_action(context, action):
        return KeyEditResult(False, problem=f"bilinmeyen eylem: {action}")
    current = load_keymap(path).bindings(context)
    holder = current.get(canonical)
    if holder is not None and holder != action and not force:
        return KeyEditResult(False, conflict=holder)
    defaults = default_keymap().get(context, {})

    def change(table: Table) -> None:
        _drop_action_keys(table, current, defaults, action, keep=canonical)
        if defaults.get(canonical) == action:
            table.pop(canonical, None)
        else:
            table[canonical] = action

    _edit(path, context, change)
    return KeyEditResult(True)


def unbind_action(path: Path, context: str, action: str) -> KeyEditResult:
    """Eylemin bütün tuşlarını kaldır (eylem paletten çalışmaya devam eder)."""
    if not is_valid_action(context, action):
        return KeyEditResult(False, problem=f"bilinmeyen eylem: {action}")
    current = load_keymap(path).bindings(context)
    defaults = default_keymap().get(context, {})
    _edit(path, context, lambda table: _drop_action_keys(table, current, defaults, action))
    return KeyEditResult(True)


def reset_action(
    path: Path, context: str, action: str | None, *, force: bool = False
) -> KeyEditResult:
    """Eylemi (ya da `None` ile bütün bağlamı) varsayılana döndür.

    Ölçüldü (31 Ekim): eylemin varsayılan tuşunu başka bir eylem devraldıysa (`mod+k: terminal`)
    sıfırlama yalnız eylemin kendi girdilerini sildiği için ok:true dönüp hiçbir şey yapmıyordu.
    Artık o tuş için çakışma döner; `force` ile tuş tutan eylemden alınır.
    """
    if action is not None and not is_valid_action(context, action):
        return KeyEditResult(False, problem=f"bilinmeyen eylem: {action}")
    defaults = default_keymap().get(context, {})
    if action is None:
        _edit(path, context, lambda table: table.clear())
        return KeyEditResult(True)
    current = load_keymap(path).bindings(context)
    taken = {
        key: current[key]
        for key, value in defaults.items()
        if value == action and current.get(key) not in (None, action)
    }
    if taken and not force:
        key, holder = next(iter(taken.items()))
        return KeyEditResult(False, conflict=holder, key=key)

    def change(table: Table) -> None:
        for key, value in list(table.items()):
            if value == action or key in taken or (value is None and defaults.get(key) == action):
                del table[key]

    _edit(path, context, change)
    return KeyEditResult(True)


def _drop_action_keys(
    table: Table,
    current: dict[str, str],
    defaults: dict[str, str],
    action: str,
    keep: str | None = None,
) -> None:
    """Eyleme şu an bağlı tuşları kaldır: varsayılan bağ `null` olur, kullanıcı bağı silinir."""
    for key, value in current.items():
        if value != action or key == keep:
            continue
        if defaults.get(key) == action:
            table[key] = None
        else:
            table.pop(key, None)


def _edit(path: Path, context: str, change: Callable[[Table], None]) -> None:
    raw = _read_raw(path)
    section = raw.get(context)
    table: Table = {}
    if isinstance(section, dict):
        for key, value in section.items():
            canonical, _ = normalize_key(context, key)
            # Okunamayan girdi olduğu gibi kalır: kullanıcı onu `/keybindings` uyarısından düzeltir.
            table[canonical or str(key)] = value
    change(table)
    if table:
        raw[context] = table
    else:
        raw.pop(context, None)
    atomic_replace_text(path, json.dumps(raw, ensure_ascii=False, indent=2) + "\n")


def _read_raw(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError(
            f"{path} okunamadı ({error}); üstüne yazılmadı. Dosyayı düzeltip yeniden dene."
        ) from error
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: kök bir sözlük olmalı; üstüne yazılmadı.")
    return raw
