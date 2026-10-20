"""Satır içi Python kodunun zararsızlık kanıtı (`inline_python`)."""

from __future__ import annotations

import pytest

from fusion_cli.tools.inline_python import is_inert_python


@pytest.mark.parametrize(
    "kod",
    [
        "print('merhaba')",
        "print(2 + 2, len('abc'))",
        "import sys; print(sys.version_info.major)",
        "import math; print(math.sqrt(16))",
        "print(f'{1 + 1:>4}')",
        "print(sorted({3, 1, 2}))",
    ],
)
def test_yalniz_bilgi_yazdiran_kod_zararsiz_sayilir(kod):
    assert is_inert_python(kod) is True


@pytest.mark.parametrize(
    "kod",
    [
        "",
        "print(",
        "open('a.txt', 'w').write('x')",
        "import os",
        "from os import system",
        "import sys; sys.stdout.write('x')",
        "print(type(1).__subclasses__())",
        "print(sys.version)",
        "print([x for x in range(3)])",
        "print((lambda: 1)())",
        "print(*range(3))",
        "print(eval('1'))",
        "import sys; print(sys._getframe())",
    ],
)
def test_kanitlanamayan_kod_zararsiz_sayilmaz(kod):
    assert is_inert_python(kod) is False
