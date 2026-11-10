"""Doğrusal okuyucu kapalı/açık işaretleme içindeki kod sınıflarını korur."""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.technical_evidence import unbacked_technical_literals


@pytest.mark.parametrize(
    ("target", "missing"),
    [
        ("<script>`erase_item`</script>`write_item`", ("write_item",)),
        ("<style>`erase_item`</style>`write_item`", ("write_item",)),
        ("<pre>`erase_item`</pre>`write_item`", ("write_item",)),
        ("<!-- `erase_item` -->`write_item`", ("write_item",)),
        ("<script>`erase_item`", ("erase_item",)),
        ("<code>`erase_item`", ("erase_item",)),
        ("<script><script>`erase_item`</script>`write_item`", ("write_item",)),
        ("<code><code>erase_item</code>", ("erase_item",)),
        ("<code>`erase_item`</code>", ()),
        ("<code>erase_item</code><code>write_item</code>", ("erase_item", "write_item")),
        ("```python\n`erase_item`\n```\n`write_item`", ("write_item",)),
        ("<pre>```python\n`erase_item`\n</pre>`write_item`", ("write_item",)),
    ],
)
def test_markup_compatibility_keeps_observation_scope(target, missing):
    assert unbacked_technical_literals(target, ("Module contents.",)) == missing


def test_duplicate_normalization_does_not_borrow_an_authored_example_exclusion():
    target = "For this example, `erase_item` is our variable. `erase_item` was removed."

    assert unbacked_technical_literals(target, ("Module contents.",)) == ("erase_item",)
