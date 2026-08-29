"""Projenin doğrulama komutlarını dosya izlerinden keşfet.

Komut kapısı opt-in olduğu için pratikte hiç kurulmuyordu: `verification_commands`
boş kaldıkça agent'ın yazdığı kodu mekanik olarak sınayan hiçbir şey çalışmıyor,
kapı yalnızca web çıktısına bakıyordu.

Çözüm komutları VARSAYMAK değil, ÖNERMEKTİR. Bu modül yalnızca bir plan üretir;
planı çalıştırma kararı kullanıcıya aittir (`/verify` komutu, `config.yaml`'a yazar).
Yanlış bir varsayılan (ör. olmayan bir test paketi) kapıyı her turda düşürür ve
agent gerçek olmayan bir hatayı düzeltmeye çalışırdı.

Keşif YALNIZCA dosya sistemine bakar, hiçbir komut çalıştırmaz.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

#: Node paket yöneticileri: lock dosyası → komut öneki. Sıra anlamlıdır, ilk
#: eşleşen kazanır; npm en sonda çünkü lock dosyası olmadan da varsayılandır.
_NODE_LOCKS = (
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("bun.lockb", "bun"),
    ("package-lock.json", "npm"),
)

#: `package.json` içinde doğrulama sayılan script adları — ucuzdan pahalıya.
_NODE_SCRIPTS = ("lint", "typecheck", "test")

#: OTOMATİK kapının kullandığı script adları.
#
# Test paketi dışarıdadır ve bu bilinçlidir: otomatik kapının cevaplaması gereken
# soru "kodu BOZDUM mu", "tüm testler geçiyor mu" değil. Kullanıcının projesinde
# önceden kırık bir test varsa, agent'ın her turu onun yüzünden düşerdi ve agent
# kendi yapmadığı bir hatayı düzeltmeye çalışırdı. `build` içeridedir çünkü
# TypeScript/Next projelerinde sözdizimini ve tipleri asıl orası denetler.
#
# `lint` DIŞARIDADIR ve bu ölçülmüş bir karardır: yapılandırılmamış bir projede
# `next lint` "How would you like to configure ESLint?" diye ETKİLEŞİMLİ soru
# sorup çıkış 1 veriyor. Kapı bunu gerçek bir kod hatası sanıp turu düşürüyor —
# kullanıcının kodunda hiçbir sorun yokken. Linter bir stil kapısıdır; otomatik
# kapının cevaplaması gereken soru "kodu BOZDUM mu" ve onu `typecheck`/`build`
# kesin olarak cevaplıyor.
_AUTO_NODE_SCRIPTS = ("typecheck", "build")

#: Makefile'da doğrulama sayılan hedefler.
_MAKE_TARGETS = ("check", "test")


def discover_auto_commands(root: Path) -> tuple[str, ...]:
    """OTOMATİK kapı için doğrulama planı: hızlı ve yalnızca "bozdum mu" sorusu.

    Ölçüldü: kapı opt-in olduğu için pratikte hiç kurulmuyordu ve bunun bedeli
    ölçüldü — agent bir TSX dosyasının ortasına beş kapanış etiketi ekledi, dosya
    12 sözdizimi hatasıyla bozuldu ve tur "tamamladım" diyerek kapandı. Bozuk kod
    teslim edip başarı iddia etmek, hiç yazmamaktan kötüdür.

    Yalnızca projede KANITI olan komutlar önerilir (var olan script, tanımlı
    hedef); uydurulmuş bir komut kapıyı her turda düşürürdü.
    """
    return discover_commands(root, node_scripts=_AUTO_NODE_SCRIPTS, include_tests=False)


def discover_commands(
    root: Path,
    *,
    node_scripts: tuple[str, ...] = _NODE_SCRIPTS,
    include_tests: bool = True,
) -> tuple[str, ...]:
    """Proje kökünden doğrulama planı çıkar. Bulunamazsa boş demet.

    Sıra MALİYETE göredir: lint → tip denetimi → test. Kapı ilk başarısız komutta
    durur; pahalı olan öne alınsaydı her kırık turda boşuna beklenirdi.
    """
    for kesif in (_python, _node, _rust, _go, _make):
        plan = kesif(root) if kesif is not _node else _node(root, node_scripts)
        if plan:
            return (
                plan
                if include_tests
                else tuple(komut for komut in plan if not _is_test_command(komut))
            )
    return ()


#: Test çalıştıran komutlar — otomatik kapıda atlanır.
_TEST_MARKERS = ("pytest", "cargo test", "go test", "run test")


def _is_test_command(command: str) -> bool:
    return any(marker in command for marker in _TEST_MARKERS)


def _python(root: Path) -> tuple[str, ...]:
    metin = _read(root / "pyproject.toml")
    if metin is None:
        return ()
    plan: list[str] = []
    if "ruff" in metin:
        plan.append("ruff check .")
    if "mypy" in metin:
        plan.append("mypy src" if (root / "src").is_dir() else "mypy .")
    if "pytest" in metin:
        plan.append("pytest -q")
    return tuple(plan)


def _node(root: Path, scripts: tuple[str, ...] = _NODE_SCRIPTS) -> tuple[str, ...]:
    metin = _read(root / "package.json")
    if metin is None:
        return ()
    try:
        veri = json.loads(metin)
    except ValueError:
        # Bozuk `package.json` keşfi durdurur ama turu düşürmez: keşif bir
        # iyileştirmedir, zorunlu bir adım değil.
        return ()
    mevcut = veri.get("scripts") if isinstance(veri, dict) else None
    if not isinstance(mevcut, dict):
        return ()
    yonetici = next((ad for dosya, ad in _NODE_LOCKS if (root / dosya).exists()), "npm")
    return tuple(f"{yonetici} run {ad}" for ad in scripts if ad in mevcut)


def _rust(root: Path) -> tuple[str, ...]:
    return ("cargo test",) if (root / "Cargo.toml").exists() else ()


def _go(root: Path) -> tuple[str, ...]:
    return ("go test ./...",) if (root / "go.mod").exists() else ()


def _make(root: Path) -> tuple[str, ...]:
    metin = _read(root / "Makefile")
    if metin is None:
        return ()
    # Yalnızca gerçekten TANIMLI hedef önerilir; olmayan hedef `make` hatası verir
    # ve kapı, projenin kendi sorunu değilken düşer.
    tanimli = {eslesme.group(1) for eslesme in re.finditer(r"^([A-Za-z0-9_-]+):", metin, re.M)}
    return tuple(f"make {ad}" for ad in _MAKE_TARGETS if ad in tanimli)


def _read(path: Path) -> str | None:
    """Dosyayı oku; yoksa ya da okunamıyorsa None."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
