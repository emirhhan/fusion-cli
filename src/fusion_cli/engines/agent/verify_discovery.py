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

import ast
import json
import re
import shlex
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from email.parser import Parser
from functools import partial
from importlib import metadata
from pathlib import Path, PurePosixPath

from ...core.evidence import EvidenceEnvironment
from ...core.read_budget import ReadBudget, ReadBudgetExceededError
from ...core.repo_imports import (
    GRAPH_SUFFIXES,
    ImportRef,
    ModuleIndex,
    build_graph,
    related_tests,
)
from ...core.workspace_fingerprint import content_digest, take_fingerprint
from .domain_adapters.defaults import default_domain_registry
from .domain_adapters.registry import DomainRegistry

#: Node paket yöneticileri: lock dosyası → komut öneki. Sıra anlamlıdır, ilk
#: eşleşen kazanır; npm en sonda çünkü lock dosyası olmadan da varsayılandır.
_NODE_LOCKS = (
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("bun.lockb", "bun"),
    # Bun ≥ 1.2 metin kilit dosyası (A4-23).
    ("bun.lock", "bun"),
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
    plan = discover_commands(
        root, node_scripts=_AUTO_NODE_SCRIPTS, include_tests=False, domains=domains
    )
    if plan:
        return plan
    # Rust/Go'da tek komut test olduğu için süzülünce kapı BOŞ kalıyordu (A4-22): derleme
    # denetimi "bozdum mu" sorusunu testsiz cevaplar.
    if (root / "Cargo.toml").exists():
        return ("cargo check",)
    if (root / "go.mod").exists():
        return ("go vet ./...",)
    return ()


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
_TEST_MARKERS = ("pytest", "cargo test", "go test", "run test", "make test")


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
    # Sarmalayıcılar ve diğer ekosistemlerin koşucuları (A4-23: "davranış kanıtlanmadı"
    # uyarısı gerçek testlerde de çıkıyordu).
    ("uv", ("run", "pytest")),
    ("poetry", ("run", "pytest")),
    ("python", ("unittest",)),
    ("python3", ("unittest",)),
    ("tox", ()),
    ("nox", ()),
    ("npx", ("playwright", "test")),
    ("playwright", ("test",)),
    ("deno", ("test",)),
    ("mvn", ("test",)),
    ("gradle", ("test",)),
    ("gradlew", ("test",)),
    ("dotnet", ("test",)),
    ("rspec", ()),
    ("bundle", ("exec", "rspec")),
    ("phpunit", ()),
)

#: `npm run test:unit` gibi `test:` önekli betikler de testtir.
_NODE_RUNNERS = frozenset({"npm", "yarn", "pnpm", "bun"})

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


#: Dosya tanıtıcı yönlendirmeleri: `2>&1`, `>&2`, `2>&-`, `&>dosya`, `&>>dosya`.
#:
#: `&` burada bir ARKA PLAN işleci değildir. Ölçüldü (29 Ekim): `pytest -q 2>&1`
#: shlex'te `['pytest','-q','2>','&','1']` çıkar; `&` maskeleme işleci sanılıp
#: komut davranış kanıtı SAYILMIYORDU (A4-04). Gerçek arka plan `cmd &` ve boru
#: korunur: yalnız bu yönlendirme kalıpları silinir.
_FD_REDIRECT = re.compile(r"(?<![\w&])\d*>&(?:\d+|-)(?![\w])|(?<![\w&])&>>?[ \t]*[^\s;&|]+")


def strip_fd_redirects(command: str) -> str:
    """`2>&1` / `&>dosya` gibi yönlendirmeleri sil; `&` arka plan işleci olarak kalır."""
    return _FD_REDIRECT.sub(" ", command)


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
        tokens = list(_command_tokens(command))
    except ValueError:
        return False
    tokens = list(_strip_setup_prefix(tuple(tokens)))
    if not tokens or any(
        token in _QUERY_FLAGS or token in _EXIT_MASKING_OPERATORS for token in tokens
    ):
        return False
    program = PurePosixPath(tokens[0]).name
    # `+nightly` (rustup araç zinciri seçici) alt komut değildir.
    arguments = [token for token in tokens[1:] if not token.startswith(("-", "+"))]
    if (
        program in _NODE_RUNNERS
        and arguments[:1] == ["run"]
        and len(arguments) > 1
        and arguments[1].startswith("test:")
    ):
        return True
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


def _declared(metin: str, ad: str) -> bool:
    """`pyproject.toml` aracı gerçekten TANIMLIYOR mu (`[tool.<ad>]` ya da bağımlılık).

    Düz alt dize testi yorumda geçen ya da `ruff-lsp` gibi başka paketin adına takılıyordu
    (A4-21). Ayrıştırma başarısızsa eski alt dize davranışına dönülür.
    """
    try:
        veri = tomllib.loads(metin)
    except tomllib.TOMLDecodeError:
        return ad in metin
    adlar: set[str] = set(veri.get("tool", {}))

    def topla(deger: object) -> None:
        if isinstance(deger, str):
            eslesme = re.match(r"[A-Za-z0-9_.-]+", deger.strip())
            if eslesme:
                adlar.add(eslesme.group(0).lower().replace("_", "-"))
        elif isinstance(deger, dict):
            for anahtar, alt in deger.items():
                adlar.add(str(anahtar).lower().replace("_", "-"))
                topla(alt)
        elif isinstance(deger, list):
            for alt in deger:
                topla(alt)

    for bolum in (
        veri.get("project"),
        veri.get("dependency-groups"),
        veri.get("tool", {}).get("poetry"),
    ):
        topla(bolum)
    return ad in adlar


def _tool(root: Path, ad: str) -> str:
    """Araç yalnız projenin sanal ortamında kuruluysa onun yolunu kullan.

    Ölçüldü (29 Ekim, A4-21): `ruff`/`mypy` yalnız `.venv` içindeyken PATH'te bulunmuyor,
    kapı 127 verip "doğrulanamadı" diyordu; Python kapısı pratikte işlevsizdi.
    """
    yol = root / ".venv" / "bin" / ad
    return f".venv/bin/{ad}" if yol.is_file() else ad


def _python(root: Path) -> tuple[str, ...]:
    metin = _read(root / "pyproject.toml")
    if metin is None:
        return ()
    plan: list[str] = []
    if _declared(metin, "ruff"):
        plan.append(f"{_tool(root, 'ruff')} check .")
    if _declared(metin, "mypy"):
        hedef = "src" if (root / "src").is_dir() else "."
        plan.append(f"{_tool(root, 'mypy')} {hedef}")
    if _declared(metin, "pytest"):
        plan.append(f"{_tool(root, 'pytest')} -q")
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


#: Kapsam taramasında tanınan ekosistemler (`make` hariç: Makefile çoğu projede
#: sarmalayıcıdır, ayrı bir ekosistem değildir).
_COVERAGE_ECOSYSTEMS: tuple[tuple[str, Callable[[Path], tuple[str, ...]]], ...] = (
    ("python", _python),
    # `build` de doğrulama sayılır: otomatik kapı TS/Next projesini onunla denetler.
    ("node", partial(_node, scripts=(*_NODE_SCRIPTS, "build"))),
    ("rust", _rust),
    ("go", _go),
)

#: Alt klasör taramasında atlanan bağımlılık/üretim dizinleri.
_COVERAGE_SKIP_DIRS = frozenset(
    {"node_modules", "venv", "vendor", "dist", "build", "target", "site-packages", "__pycache__"}
)

#: Raporda en çok kaç kapsam dışı ekosistem sayılır.
_COVERAGE_REPORT_LIMIT = 5


def uncovered_ecosystems(root: Path, *, domains: DomainRegistry | None = None) -> tuple[str, ...]:
    """Otomatik kapının DOĞRULAMADIĞI ekosistemleri adlandır (A4-66).

    Keşif kökte tek ekosistem seçer ("ilk dolu kazanır"). Ölçüldü (30 Ekim): bu depo
    `pyproject.toml` + `app/` (Tauri/React) olduğu için `app/` altındaki TypeScript
    derlemesi ve tipi hiç denetlenmiyor, ama kullanıcı bunu hiçbir yerde görmüyordu.

    Kökte seçilenin dışında kalan ekosistemler ve bir alt klasördeki (ör. `app/`)
    doğrulanabilir projeler `"app/ (node)"` biçiminde döner. Yalnız dosya sistemine
    bakar, komut çalıştırmaz.
    """
    registry = domains if domains is not None else default_domain_registry()
    root_hits = [label for label, discover in _COVERAGE_ECOSYSTEMS if discover(root)]
    # Alan kapısı (Godot vb.) node'dan sonra ve rust'tan önce seçilir (bkz. `discover_commands`).
    if registry.gate_commands(root):
        root_hits.insert(min(len(root_hits), 2 if "node" in root_hits else 1), "alan")
    rapor = [f"{label} (kök)" for label in root_hits[1:]]
    try:
        children = sorted(path for path in root.iterdir() if path.is_dir())
    except OSError:
        children = []
    for child in children:
        if child.name.startswith(".") or child.name in _COVERAGE_SKIP_DIRS:
            continue
        rapor.extend(
            f"{child.name}/ ({label})"
            for label, discover in _COVERAGE_ECOSYSTEMS
            if discover(child)
        )
    return tuple(rapor[:_COVERAGE_REPORT_LIMIT])


def _read(path: Path) -> str | None:
    """Dosyayı oku; yoksa ya da okunamıyorsa None."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


#: Yalnız bilinen doğrulama girdileri okunur; ortam değişkenleri ve sır dosyaları okunmaz.
_EVIDENCE_LOCKFILES = (
    "uv.lock",
    "poetry.lock",
    "Pipfile.lock",
    "requirements.txt",
    "requirements-dev.txt",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lock",
    "bun.lockb",
    "package-lock.json",
    "Cargo.lock",
    "go.sum",
    "composer.lock",
    "Gemfile.lock",
)
_EVIDENCE_CONFIGS = (
    "pyproject.toml",
    "pytest.ini",
    ".pytest.ini",
    "tox.ini",
    "setup.cfg",
    "ruff.toml",
    ".ruff.toml",
    "mypy.ini",
    ".mypy.ini",
    "package.json",
    "tsconfig.json",
    "vitest.config.ts",
    "vitest.config.js",
    "vite.config.ts",
    "vite.config.js",
    "jest.config.js",
    "jest.config.ts",
    "jest.config.mjs",
    "jest.config.cjs",
    "playwright.config.ts",
    "Cargo.toml",
    "go.mod",
    "Makefile",
)


@dataclass(frozen=True, slots=True)
class CommandEnvironment:
    """Desteklenen kurulum öneklerinden sonraki gerçek dizin ve koşucu argümanları."""

    cwd: Path
    tokens: tuple[str, ...]


def _command_tokens(command: str) -> tuple[str, ...]:
    """Davranış ve ortam çözümlemesi için aynı kabuk tokenlarını üret."""
    lexer = shlex.shlex(strip_fd_redirects(command), posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    return tuple(lexer)


def command_environment(
    root: Path, command: str, *, read_budget: ReadBudget | None = None
) -> CommandEnvironment | None:
    """Yalnız kök içindeki açık cd öneklerini çöz; belirsiz kabukta önbellek yok."""
    try:
        if read_budget is not None:
            read_budget.entry()
        root = root.resolve()
        tokens = _command_tokens(command)
        cwd = root
        remaining = tokens
        while remaining and remaining[0] == "cd":
            if read_budget is not None:
                read_budget.entry()
            if len(remaining) < 3 or remaining[2] not in {"&&", ";"}:
                return None
            target = remaining[1]
            if any(marker in target for marker in ("$", "~", "*", "?", "`")):
                return None
            cwd = (cwd / target).resolve()
            if not cwd.is_relative_to(root) or not cwd.is_dir():
                return None
            remaining = remaining[3:]
        effective = _strip_setup_prefix(tokens)
        if effective != remaining or not effective or not cwd.is_dir():
            return None
        if any(token in {"&&", "||", "|", ";", "&", "(", ")"} for token in effective):
            return None
        if any("$" in token or "`" in token for token in effective):
            return None
        return CommandEnvironment(cwd, effective)
    except (OSError, ValueError, RuntimeError):
        return None


def evidence_environment(
    root: Path,
    commands: tuple[str, ...],
    *,
    runtime: str,
    runner_paths: tuple[Path, ...] = (),
    read_budget: ReadBudget | None = None,
) -> EvidenceEnvironment | None:
    """Güvenle ölçülen etkin proje girdilerini özetle; belirsizlikte cache'i kapat."""
    if read_budget is not None:
        try:
            read_budget.check()
        except ReadBudgetExceededError:
            return None
    root = root.resolve()
    environments = [
        command_environment(root, command, read_budget=read_budget) for command in commands
    ]
    if not environments or any(item is None for item in environments):
        return None
    known = [item for item in environments if item is not None]
    runners = {Path(sys.executable), Path(sys.executable).resolve(), *runner_paths}
    configs: set[Path] = set()
    dependencies: set[Path] = set()
    distributions: set[str] = set()
    try:
        for item in known:
            for ancestor in _project_ancestors(root, item.cwd):
                configs.update(ancestor / name for name in _EVIDENCE_CONFIGS)
                dependencies.update(ancestor / name for name in _EVIDENCE_LOCKFILES)
            configs.update(_explicit_configs(item.cwd, list(item.tokens)))
            program = Path(item.tokens[0])
            candidate = selected_runner_module(item) or program.name
            if candidate in _RUNNER_DISTRIBUTIONS:
                distributions.add(candidate)
            runners.add(program if program.is_absolute() else item.cwd / program)
            runners.add(item.cwd / ".venv" / "bin" / program.name)
        if any(part.startswith(".env") for runner in runners for part in runner.parts):
            return None
        safe_configs = _environment_paths(root, configs, read_budget=read_budget)
        safe_dependencies = _environment_paths(root, dependencies, read_budget=read_budget)
        if safe_configs is None or safe_dependencies is None:
            return None
        runner_digest = content_digest(runners, strict=True, read_budget=read_budget)
        versions = _runner_versions(distributions, read_budget=read_budget)
        return EvidenceEnvironment(
            command="\n".join(commands),
            cwd="\n".join(str(item.cwd) for item in known),
            runtime=f"{runtime}:{versions}:{runner_digest}",
            dependency_digest=content_digest(
                safe_dependencies, strict=True, read_budget=read_budget
            ),
            config_digest=content_digest(safe_configs, strict=True, read_budget=read_budget),
        )
    except (OSError, ValueError, RuntimeError):
        return None


def _project_ancestors(root: Path, cwd: Path) -> tuple[Path, ...]:
    """Koşucunun üst dizin keşfini yalnız izin verilen proje köküne kadar kapsa."""
    ancestors = []
    current = cwd
    while current.is_relative_to(root):
        ancestors.append(current)
        if current == root:
            return tuple(ancestors)
        current = current.parent
    raise ValueError("Etkin çalışma dizini izin verilen proje kökü dışında.")


def _environment_paths(
    root: Path, paths: set[Path], *, read_budget: ReadBudget | None = None
) -> tuple[Path, ...] | None:
    """Bağ kimliğiyle birlikte izin verilen hedef içeriğini de ölçüme ekle."""
    expanded: set[Path] = set()
    for path in paths:
        if read_budget is not None:
            read_budget.entry()
        target = path.resolve()
        if not target.is_relative_to(root) or any(
            part.startswith(".env") for part in target.relative_to(root).parts
        ):
            return None
        if path.is_symlink() and not target.is_file():
            return None
        expanded.update((path, target))
    return tuple(sorted(expanded))


def selected_runner_module(environment: CommandEnvironment) -> str | None:
    """Yalnız seçilmiş python -m koşucu modülünü döndür; ürün importlarını sınıflama."""
    tokens = environment.tokens
    if not Path(tokens[0]).name.startswith("python") or "-m" not in tokens:
        return None
    module_index = tokens.index("-m") + 1
    module = tokens[module_index] if module_index < len(tokens) else ""
    return module if module in _RUNNER_DISTRIBUTIONS else None


_CONFIG_OPTIONS = frozenset({"-c", "--config", "--config-file", "-p", "--project"})


def _explicit_configs(root: Path, tokens: list[str]) -> set[Path]:
    """Komuttaki açık test/derleme yapılandırmasını kök sınırı içinde kimliğe kat."""
    configs: set[Path] = set()
    for index, token in enumerate(tokens):
        option, separator, inline = token.partition("=")
        if option not in _CONFIG_OPTIONS:
            continue
        value = inline if separator else tokens[index + 1] if index + 1 < len(tokens) else ""
        if not value:
            continue
        # Güvenlik kararı tüm girdilerle birlikte _environment_paths sınırında verilir.
        configs.add(root / value)
    return configs


_RUNNER_DISTRIBUTIONS = frozenset({"pytest", "ruff", "mypy", "tox", "nox"})


def _runner_versions(distributions: set[str], *, read_budget: ReadBudget | None = None) -> str:
    """Yalnız seçilmiş Python koşucularının kurulu sürüm kaydını oku; paket kurma."""
    versions = []
    for distribution in sorted(distributions):
        try:
            version = (
                metadata.version(distribution)
                if read_budget is None
                else _bounded_runner_version(distribution, read_budget)
            )
        except metadata.PackageNotFoundError:
            version = "kurulu-degil"
        versions.append(f"{distribution}:{version}")
    return ";".join(versions)


def _bounded_runner_version(distribution: str, budget: ReadBudget) -> str:
    """Read standard installed metadata with the same entry/byte/deadline budget."""
    target = distribution.replace("_", "-").lower()
    for base in dict.fromkeys(sys.path):
        budget.check()
        directory = Path(base or ".")
        if directory.is_file():
            # Archive/custom metadata providers have no bounded read contract.
            raise ValueError("Unbounded distribution metadata unavailable.")
        try:
            for entry in budget.iterdir(directory):
                suffix = next(
                    (
                        suffix
                        for suffix in (".dist-info", ".egg-info")
                        if entry.name.endswith(suffix)
                    ),
                    "",
                )
                if (
                    not suffix
                    or entry.name[: -len(suffix)].split("-", 1)[0].replace("_", "-").lower()
                    != target
                ):
                    continue
                name = "METADATA" if suffix == ".dist-info" else "PKG-INFO"
                text = budget.read_bytes(Path(entry.path) / name).decode("utf-8")
                version = Parser().parsestr(text).get("Version")
                if not version:
                    raise ValueError("Distribution version unavailable.")
                return str(version)
        except (FileNotFoundError, NotADirectoryError):
            continue
    return "kurulu-degil"


def source_digest(root: Path, *, read_budget: ReadBudget | None = None) -> str:
    """Mevcut içerik özetleyiciyle kaynak/test dosyalarını ölç; sır dosyalarını okuma."""
    try:
        snapshot = take_fingerprint(root, read_budget=read_budget)
    except ReadBudgetExceededError:
        return ""
    if snapshot is None:
        return ""
    paths = tuple(
        root / name
        for name in snapshot
        if Path(name).suffix in GRAPH_SUFFIXES
        and not any(part.startswith(".env") for part in Path(name).parts)
    )
    try:
        return content_digest(paths, strict=True, read_budget=read_budget)
    except (OSError, ReadBudgetExceededError):
        return ""


def _is_python_test(path: str) -> bool:
    name = PurePosixPath(path).name
    return name.startswith("test_") or name.endswith("_test.py")


def related_test_command(root: Path, command: str, changed: tuple[str, ...]) -> str:
    """Yalnız yalın tam-pytest komutunu güvenle daralt; belirsizlikte aynen bırak."""
    environment = command_environment(root, command)
    if environment is None or environment.cwd != root.resolve():
        return command
    tokens = environment.tokens
    runner = 3 if selected_runner_module(environment) == "pytest" else 1
    if runner == 1 and Path(tokens[0]).name != "pytest":
        return command
    # Seçici/yapılandırma/dizin argümanları anlaşılmadan üzerine yeni kapsam eklenmez.
    if any(token not in {"-q", "-v", "-x", "--disable-warnings"} for token in tokens[runner:]):
        return command
    snapshot = take_fingerprint(root)
    if snapshot is None:
        return command
    paths = tuple(name for name in snapshot if name.endswith(".py"))
    if any(PurePosixPath(path).name == "conftest.py" for path in paths) or _custom_test_discovery(
        root
    ):
        return command
    if any(not path.endswith(".py") for path in changed):
        return command
    imports = {}
    try:
        for path in paths:
            source_path = root / path
            if source_path.is_symlink() or any(
                part.startswith(".env") for part in Path(path).parts
            ):
                return command
            source = source_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            if any(_has_dynamic_import(node) for node in ast.walk(tree)):
                return command
            imports[path] = _python_import_refs(tree)
    except (OSError, UnicodeError, SyntaxError):
        return command
    graph = build_graph(imports, ModuleIndex.build(paths), is_test=_is_python_test)
    selected = related_tests(graph, changed, is_test=_is_python_test)
    return shlex.join((*tokens, *selected)) if selected else command


def _python_import_refs(tree: ast.AST) -> list[ImportRef]:
    """Bütün geçerli Python importlarını mevcut grafın sözleşmesine dönüştür."""
    references: list[ImportRef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            references.extend(ImportRef(alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            references.append(
                ImportRef(
                    node.module or "",
                    tuple(alias.name for alias in node.names),
                    node.level,
                )
            )
    return references


_CUSTOM_TEST_DISCOVERY = re.compile(
    r"\b(?:python_files|python_classes|python_functions|required_plugins|pytest_plugins)\b"
    r"|(?:^|[\s\"'])(?:-p|--pyargs|--ignore|--deselect)(?:[=\s\"']|$)"
)
_TEST_DISCOVERY_CONFIGS = ("pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml")


def _custom_test_discovery(root: Path) -> bool:
    """Grafın bilmediği test adlandırması veya eklenti ayarı varsa tam kapıya dön."""
    root = root.resolve()
    for name in _TEST_DISCOVERY_CONFIGS:
        path = root / name
        if not path.exists():
            continue
        target = path.resolve()
        if not target.is_relative_to(root) or any(part.startswith(".env") for part in target.parts):
            return True
        try:
            if _CUSTOM_TEST_DISCOVERY.search(path.read_text(encoding="utf-8")):
                return True
        except (OSError, UnicodeError):
            return True
    return False


def _has_dynamic_import(node: ast.AST) -> bool:
    """Dinamik yükleme ve yıldız importu statik ilişkiyi belirsiz kılar."""
    if isinstance(node, ast.Name) and node.id == "pytest_plugins":
        return True
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        modules = (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
        )
        if any(module.split(".")[0] in {"importlib", "pkgutil", "runpy"} for module in modules):
            return True
    if isinstance(node, ast.ImportFrom):
        return any(alias.name == "*" for alias in node.names)
    if not isinstance(node, ast.Call):
        return False
    function = node.func
    return (isinstance(function, ast.Name) and function.id in {"__import__", "exec", "eval"}) or (
        isinstance(function, ast.Attribute) and function.attr in {"import_module", "load_module"}
    )
