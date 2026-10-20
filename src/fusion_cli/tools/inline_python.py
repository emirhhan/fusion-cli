"""Satır içi Python kodunun (`python3 -c "..."`) KANITLANABİLİR biçimde zararsızlığı.

`python -c` keyfi kod çalıştırır; bu yüzden varsayılan cevap "sor"dur. Ama modelin
sık yaptığı kontrol — `python3 -c "import sys; print(sys.version)"` — hiçbir şeye
dokunmaz ve her seferinde onay istemek auto kipini yoruyordu (17 Eylül denetimi, B6).

Buradaki karar bir kara liste DEĞİLDİR. Kod ayrıştırılır ve YALNIZCA şu biçim geçer:
izinli modülleri içe aktaran ve izinli fonksiyonları sabit/basit ifadelerle çağıran
ifade satırları. Dosya açmak (`open`), içe aktarma hilesi (`__import__`), öznitelik
zinciri üzerinden çağrı (`sys.modules[...]`), döngü, atama, lambda — hiçbiri
tanınmadığı için geçemez. Kanıtlayamadığımız kod yine sorulur.
"""

from __future__ import annotations

import ast

#: Yan etkisiz yerleşik fonksiyonlar. `open`, `exec`, `eval`, `__import__`,
#: `getattr`, `input` bilinçli olarak yok.
_SAFE_BUILTINS = frozenset(
    {
        "print", "len", "repr", "str", "int", "float", "bool", "sorted", "min",
        "max", "sum", "abs", "round", "list", "tuple", "dict", "set", "range",
        "enumerate", "zip", "type",
    }
)  # fmt: skip

#: İçe aktarılabilen modüller ve fonksiyonları ÇAĞRILABİLİR mi?
#:
#: `sys` yalnızca OKUNUR (`sys.version`); fonksiyonları çağrılamaz, çünkü
#: `sys.remote_exec` gibi başka süreçte kod çalıştıran fonksiyonlar vardır.
#: `platform` ve `math` fonksiyonları yalnız bilgi döndürür.
_SAFE_MODULES: dict[str, bool] = {"sys": False, "platform": True, "math": True}

#: Değer üreten, kendi başına hiçbir şey çalıştırmayan düğümler.
_VALUE_NODES = (
    ast.Constant, ast.JoinedStr, ast.FormattedValue, ast.BinOp, ast.UnaryOp,
    ast.BoolOp, ast.Compare, ast.IfExp, ast.Tuple, ast.List, ast.Set, ast.Dict,
    ast.keyword, ast.Load, ast.operator, ast.unaryop, ast.boolop, ast.cmpop,
)  # fmt: skip


def is_inert_python(code: str) -> bool:
    """Kod yalnızca bilgi yazdırıyor mu? Kanıtlanamıyorsa False."""
    try:
        tree = ast.parse(code, mode="exec")
    except (SyntaxError, ValueError):
        return False
    imported: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, ast.Import):
            if not all(_is_safe_import(alias) for alias in statement.names):
                return False
            imported.update(alias.name for alias in statement.names)
        elif not (isinstance(statement, ast.Expr) and _is_inert(statement.value, imported)):
            return False
    return bool(tree.body)


def _is_safe_import(alias: ast.alias) -> bool:
    return alias.asname is None and alias.name in _SAFE_MODULES


def _is_inert(expression: ast.expr, imported: set[str]) -> bool:
    return all(_is_inert_node(node, imported) for node in ast.walk(expression))


def _is_inert_node(node: ast.AST, imported: set[str]) -> bool:
    if isinstance(node, _VALUE_NODES):
        return True
    if isinstance(node, ast.Name):
        return node.id in _SAFE_BUILTINS or node.id in imported
    if isinstance(node, ast.Attribute):
        return _module_root(node) in imported and not node.attr.startswith("_")
    if isinstance(node, ast.Call):
        return _is_safe_callee(node.func, imported)
    return False


def _module_root(node: ast.Attribute) -> str | None:
    """`sys.version_info.major` → `sys`; kök bir ad değilse None."""
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None


def _is_safe_callee(callee: ast.expr, imported: set[str]) -> bool:
    """Çağrılan şey izinli bir yerleşik ya da çağrılabilir modülün DOĞRUDAN fonksiyonu mu?"""
    if isinstance(callee, ast.Name):
        return callee.id in _SAFE_BUILTINS
    if isinstance(callee, ast.Attribute) and isinstance(callee.value, ast.Name):
        module = callee.value.id
        return module in imported and _SAFE_MODULES.get(module, False)
    return False
