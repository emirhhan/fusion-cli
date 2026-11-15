"""Adsız çalışma ağacı için Claude Code biçiminde ad (#339): `bright-running-fox`."""

from __future__ import annotations

import random

_ADJECTIVES = (
    "bright",
    "calm",
    "clever",
    "eager",
    "gentle",
    "happy",
    "lucky",
    "merry",
    "quiet",
    "rapid",
    "silent",
    "steady",
    "sunny",
    "swift",
    "wise",
    "bold",
)
_VERBS = (
    "running",
    "jumping",
    "dancing",
    "flying",
    "gliding",
    "humming",
    "racing",
    "roaming",
    "singing",
    "skipping",
    "soaring",
    "spinning",
    "wandering",
    "drifting",
    "climbing",
    "diving",
)
_NOUNS = (
    "fox",
    "otter",
    "falcon",
    "panda",
    "tiger",
    "badger",
    "heron",
    "lynx",
    "maple",
    "river",
    "comet",
    "meadow",
    "harbor",
    "pebble",
    "willow",
    "breeze",
)


def random_worktree_name(rng: random.Random | None = None) -> str:
    """`sıfat-fiil-isim` biçiminde, `validate_name` kuralına uyan ad."""
    source = rng or random.SystemRandom()
    return "-".join(source.choice(words) for words in (_ADJECTIVES, _VERBS, _NOUNS))
