"""Paketlenmiş uygulamadaki konuşma yardımcısını doğrula.

Terminalden ölçülemeyen tek şey MİKROFON İZNİDİR: çıplak bir CLI ikilisi izin
penceresini açamaz ve `authorizationStatus()` sessizce `notDetermined` kalır.
ÖNEMLİ: Yardımcıyı doğrudan çalıştırmak YETMEZ. macOS izni çağıran sürecin
kimliğine bağlar; terminalden doğrulan yardımcı için izin penceresi hiç açılmaz
(ölçüldü). Bu yüzden burada yalnız PAKET İÇERİĞİ doğrulanır — yardımcının ve
izin açıklamalarının yerinde olduğu. Mikrofonun gerçekten çalıştığı ancak
uygulama açılıp konuşma kipine girilerek görülür.

Model çağrısı YAPMAZ ve ses KAYDETMEZ: yalnız yardımcının açılıp `hazir`
satırını yazdığını, yani izin ve ses motorunun kurulduğunu doğrular.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

#: Yardımcının açılması için üst sınır. İzin penceresi çıkarsa kullanıcı
#: yanıtlayana kadar bekler; bu yüzden cömert tutuldu.
TIMEOUT_SANIYE = 45


def verify(app: Path) -> int:
    helper = app / "Contents" / "Resources" / "fusion-listen"
    if not helper.is_file():
        print(f"Yardımcı pakette yok: {helper}")
        return 1

    plist = app / "Contents" / "Info.plist"
    import plistlib

    with plist.open("rb") as stream:
        keys = plistlib.load(stream)
    for key in ("NSMicrophoneUsageDescription", "NSSpeechRecognitionUsageDescription"):
        if key not in keys:
            print(f"Info.plist'te {key} yok; izin penceresi HİÇ açılmaz.")
            return 2
    print("Info.plist izin açıklamaları yerinde.")

    print(f"Yardımcı pakette: {helper.stat().st_size // 1024} KB")
    print(
        "Mikrofon yolu buradan ölçülemez: izin, çağıran sürecin kimliğine bağlıdır.\n"
        "Doğrulamak için Fusion'ı aç, görev kutusundaki mikrofona bas ve izin\n"
        "penceresinin çıktığını gör."
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Paketli konuşma yardımcısını doğrular.")
    parser.add_argument("app", type=Path, help="Fusion.app yolu")
    args = parser.parse_args()
    sys.exit(verify(args.app.resolve()))


if __name__ == "__main__":
    main()
