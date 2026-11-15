"""Convert the pinned CMUdict source to the Turkish approximation used by Talk."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

REVISION = "74790861f652b15e4ac49015a90074ad62a27690"
PHONES = {
    "AA": "a", "AE": "e", "AH0": "ı", "AH": "a", "AO": "o", "AW": "av",
    "AY": "ay", "B": "b", "CH": "ç", "D": "d", "DH": "d", "EH": "e",
    "ER": "ır", "EY": "ey", "F": "f", "G": "g", "HH": "h", "IH": "i",
    "IY": "i", "JH": "c", "K": "k", "L": "l", "M": "m", "N": "n",
    "NG": "ng", "OW": "o", "OY": "oy", "P": "p", "R": "r", "S": "s",
    "SH": "ş", "T": "t", "TH": "t", "UH": "u", "UW": "u", "V": "v",
    "W": "v", "Y": "y", "Z": "z", "ZH": "j",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help=f"cmudict.dict at revision {REVISION}")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    words: dict[str, str] = {}
    for line in args.source.read_text(encoding="utf-8").splitlines():
        entry = line.partition("#")[0].split()
        if not entry or not re.fullmatch("[a-z]+", entry[0]):
            continue
        word, *phones = entry
        speech = "".join(PHONES[p] if p in PHONES else PHONES[p.rstrip("012")] for p in phones)
        if speech != word:
            words[word] = speech
    lines = [f"{word}\t{speech}" for word, speech in sorted(words.items())]
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
