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
import shlex
from collections.abc import Callable
from functools import partial
from pathlib import Path, PurePosixPath

from .domain_adapters.defaults import default_domain_registry
from .domain_adapters.registry import DomainRegistry

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


#: Proje KİMLİĞİ: hangi işaret dosyası hangi teknolojiyi gösterir.
#:
#: `discover_commands` ile bilinçli olarak AYRI tutulur; oradaki soru "bu projede
#: hangi komut çalışır", buradaki soru "bu ne tür bir proje". İlki ilk eşleşende
#: durur (komut planı tek olmalı), ikincisi hepsini döndürür (bir depo hem Python
#: hem Node olabilir). Aynı ayrım `_TEST_MARKERS` / `_BEHAVIORAL_RUNNERS` ikilisinde
#: de var.
_KIND_MARKERS: tuple[tuple[str, str], ...] = (
    ("godot", "project.godot"),
    ("python", "pyproject.toml"),
    ("node", "package.json"),
    ("rust", "Cargo.toml"),
    ("go", "go.mod"),
)


def project_kinds(root: Path) -> tuple[str, ...]:
    """Kökteki işaret dosyalarından proje türlerini çıkar; alfabetik ve tekrarsız.

    Ders belleği bunu kimlik olarak kullanır: "Godot MCP'de `res://` kullanma"
    dersi öğrenildiği KLASÖRE değil, öğrenildiği TEKNOLOJİYE aittir ve bir sonraki
    Godot projesinde de geçerlidir.
    """
    return tuple(sorted(ad for ad, dosya in _KIND_MARKERS if (root / dosya).exists()))


def discover_auto_commands(root: Path, *, domains: DomainRegistry | None = None) -> tuple[str, ...]:
    """OTOMATİK kapı için doğrulama planı: hızlı ve yalnızca "bozdum mu" sorusu.

    Ölçüldü: kapı opt-in olduğu için pratikte hiç kurulmuyordu ve bunun bedeli
    ölçüldü — agent bir TSX dosyasının ortasına beş kapanış etiketi ekledi, dosya
    12 sözdizimi hatasıyla bozuldu ve tur "tamamladım" diyerek kapandı. Bozuk kod
    teslim edip başarı iddia etmek, hiç yazmamaktan kötüdür.

    Yalnızca projede KANITI olan komutlar önerilir (var olan script, tanımlı
    hedef); uydurulmuş bir komut kapıyı her turda düşürürdü.
    """
    return discover_commands(
        root, node_scripts=_AUTO_NODE_SCRIPTS, include_tests=False, domains=domains
    )


def discover_commands(
    root: Path,
    *,
    node_scripts: tuple[str, ...] = _NODE_SCRIPTS,
    include_tests: bool = True,
    domains: DomainRegistry | None = None,
) -> tuple[str, ...]:
    """Proje kökünden doğrulama planı çıkar. Bulunamazsa boş demet.

    Sıra MALİYETE göredir: lint → tip denetimi → test. Kapı ilk başarısız komutta
    durur; pahalı olan öne alınsaydı her kırık turda boşuna beklenirdi.

    Alan kapıları (Godot vb.) kayıt defterinden gelir ve Node ile Rust arasındaki
    yerini korur; ilk boş olmayan keşif kazanır. `domains` verilmezse varsayılan
    kayıt o anda kurulur.
    """
    registry = domains if domains is not None else default_domain_registry()
    kesifler: tuple[Callable[[Path], tuple[str, ...]], ...] = (
        _python,
        partial(_node, scripts=node_scripts),
        registry.gate_commands,
        _rust,
        _go,
        _make,
    )
    for kesif in kesifler:
        plan = kesif(root)
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


#: Kodu GERÇEKTEN ÇALIŞTIRAN doğrulama komutları: koşucu adı → alt komutları.
#:
#: Ayrım `_TEST_MARKERS` ile aynı değildir ve olmamalıdır: orada soru "bu komut
#: pahalı/kırılgan mı, otomatik kapıda atlayayım mı"; burada soru "bu komut
#: davranışı KANITLIYOR mu". `make test` ikincisine girer, birincisine girmez.
#:
#: Kayıt metin parçası değil, KOŞUCU tutar: aynı ad birden çok kez geçebilir
#: (`npm test` ile `npm run test` aynı işi yapar). Düz metin araması yetmez —
#: `printf pytest` de "pytest" içerir ama çalıştırdığı program bambaşkadır.
_BEHAVIORAL_RUNNERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pytest", ()),
    ("vitest", ("run",)),
    ("jest", ()),
    ("npx", ("vitest", "run")),
    ("npx", ("jest",)),
    # `python -m pytest`: `-m` bayrak olarak ayıklanır, geriye `pytest` kalır.
    ("python", ("pytest",)),
    ("python3", ("pytest",)),
    ("cargo", ("test",)),
    ("go", ("test",)),
    ("make", ("test",)),
    ("npm", ("test",)),
    ("npm", ("run", "test")),
    ("yarn", ("test",)),
    ("yarn", ("run", "test")),
    ("pnpm", ("test",)),
    ("pnpm", ("run", "test")),
    ("bun", ("test",)),
    ("bun", ("run", "test")),
)

#: Koşucuyu çağırsa da tek satır test çalıştırmayan sorgu bayrakları.
_QUERY_FLAGS = frozenset({"--version", "-V", "--help", "-h", "--collect-only", "--co"})

#: Koşucunun çıkış kodunu kabuğa ulaştırmayan işleçler.
#:
#: `pytest || true` ve `pytest | tail` kırmızı testte de sıfır döner; başarılı araç
#: çağrısı olarak kaydedilen bu komut davranışı kanıtlamaz. `&&` ve zincirin
#: BAŞINDAKİ `;` burada YOKTUR — onlar `_strip_setup_prefix` tarafından ayrıca ele
#: alınır; ikisi de çıkış kodunu maskelemez, yalnızca sıralı çalıştırır.
_EXIT_MASKING_OPERATORS = frozenset({"||", "|", ";", "&"})

#: Ortam değişkeni ataması: `FOO=1`, `DEBUG=true` gibi bir öneki tanır.
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

#: Zincirin başında davranışı DEĞİŞTİRMEYEN, yalnızca ortam kuran komutlar.
#:
#: `cd X && pytest` ile `pytest` aynı davranışı kanıtlar; `cd` yalnızca çalışma
#: dizinini değiştirir. Bu yüzden `token in _EXIT_MASKING_OPERATORS` kontrolüne
#: girmeden ÖNCE bu önek ayıklanır — aksi hâlde gerçek bir doğrulama komutu, önüne
#: `cd` eklendi diye kanıtsız sayılırdı.
_SETUP_PREFIX_COMMANDS = frozenset({"cd", "source", "."})


def _strip_setup_prefix(tokens: tuple[str, ...]) -> tuple[str, ...]:
    """Zincirin başındaki zararsız kurulum önekini (cd/source/ortam değişkeni) at.

    Ölçüldü: `cd /proje && python -m pytest tests/ -v` kullanıcı tarafından
    onaylanıp çıkış kodu 0 ile bitti, ama tanıma yalnızca ilk token'a (`cd`)
    bakıp komutu davranış kanıtı SAYMADI. `cd`, `source`/`.` ve ortam değişkeni
    ataması (`FOO=1 …`) asıl komutun ÇALIŞTIĞI programı değiştirmez; yalnızca
    zincirin geri kalanının önündeki önektir.
    """
    remaining = tokens
    while remaining:
        if remaining[0] in _SETUP_PREFIX_COMMANDS:
            if len(remaining) >= 3 and remaining[2] in {"&&", ";"}:
                remaining = remaining[3:]
                continue
            break
        if _ENV_ASSIGNMENT.match(remaining[0]):
            remaining = remaining[1:]
            continue
        break
    return remaining


def is_behavioral_command(command: str) -> bool:
    """Bu komut kodu GERÇEKTEN çalıştırıp davranışı kanıtlıyor mu.

    Keşfedilen komutla ÇALIŞTIRILAN komut birebir aynı olmak zorunda değildir:
    keşif `pytest -q` önerir, agent `.venv/bin/pytest tests/test_agent_loop.py`
    çalıştırır. Ölçüldü (17 Eylül denetimi): birebir metin karşılaştırması yüzünden
    dört testi geçen gerçek bir `pytest` koşusu kanıt sayılmadı ve tur "davranış
    kanıtlanmadı" uyarısıyla kapandı.

    Gevşetme metin aramasına indirgenmez: karar komutun ÇALIŞTIRDIĞI programa ve
    alt komutuna bakar. `printf pytest` ile `pytest --version` kanıt değildir —
    biri koşucuyu hiç çağırmaz, diğeri tek satır test koşmaz.
    """
    try:
        # `punctuation_chars` ile `;`/`&`/`|` bitişik oldukları kelimeden (`S3;`
        # gibi) ayrı token olarak çıkar; düz `shlex.split` bunları harf gibi
        # yutar ve `cd yol;` önekini asla `;` token'ına dönüştürmezdi.
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        # Tırnağı kapanmayan komut ayrıştırılamaz; kanıt saymak uydurma olurdu.
        return False
    tokens = list(_strip_setup_prefix(tuple(tokens)))
    if not tokens or any(
        token in _QUERY_FLAGS or token in _EXIT_MASKING_OPERATORS for token in tokens
    ):
        return False
    program = PurePosixPath(tokens[0]).name
    arguments = [token for token in tokens[1:] if not token.startswith("-")]
    return any(
        program == name and arguments[: len(subcommands)] == list(subcommands)
        for name, subcommands in _BEHAVIORAL_RUNNERS
    )


def behavioral_commands(root: Path, *, domains: DomainRegistry | None = None) -> tuple[str, ...]:
    """Projenin, kodu çalıştırarak DAVRANIŞI kanıtlayan komutlarını döndür.

    Derleme, tip denetimi, lint ve "proje açılıyor mu" kapıları buraya GİRMEZ:
    hepsi çıktının iyi biçimli olduğunu kanıtlar, istenen işi yaptığını değil.

    Ölçülen hata: bir Godot görevi dört adımda "tamamlandı" dedi ve kabul kapısı
    geçti; `godot --headless --path . --quit` projenin AÇILDIĞINI kanıtlıyordu.
    Oysa üretilen scriptler hiçbir düğüme bağlanmamıştı ve oyun hiç çalışmıyordu.
    Kapının kanıtladığı şeyle kullanıcıya söylenen şey aynı olmalıdır.
    """
    return tuple(
        command
        for command in discover_commands(root, domains=domains)
        if is_behavioral_command(command)
    )


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
