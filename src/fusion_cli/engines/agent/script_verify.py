"""`package.json` betiklerindeki YOL ve BETİK referanslarını doğrula.

Neden var (ölçüldü, canlı koşu): kullanıcı "bağlı projeleri tek yerden kontrol
edebileyim" dedi. Model `package.json`'a şu betiği yazdı:

    "dev:ai": "sh -c 'cd ../GATE-AI && npm install && npm run dev'"

`../GATE-AI` dizini var ama içinde `package.json` YOK — uygulama `GATE-AI/web`
altında. Betik çalıştırıldığı anda patlar. Derleme kapısı bunu göremez çünkü
`npm run build` bu betiği çalıştırmaz; kullanıcı hatayı ancak günler sonra,
`npm run start:all` dediğinde bulur.

Kapı komutu ÇALIŞTIRMAZ — dosya sistemine bakar. Kardeş projeleri birbirine
bağlayan bir mega-app'te yanlış yol, en sık ve en sessiz hata sınıfıdır.
"""

from __future__ import annotations

import json
import posixpath
import re
from pathlib import Path

from ...core.verification import VerificationResult

#: `npm --prefix <yol> run <betik>` biçimi.
_PREFIX_RUN = re.compile(r"--prefix\s+(?P<path>[^\s'\"]+)(?:\s+run\s+(?P<script>[\w:.-]+))?")
#: Komut ayırıcıları: her parça kendi `cd`/`npm` çağrısını taşır.
_SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\||\n")
#: Parçadaki `cd <yol>`.
_CD = re.compile(r"(?:^|[\s'\"(])cd\s+(?P<path>[^\s'\"&;|)]+)")
#: `npm [run|run-script] <ad>` — `run` yoksa ad npm alt komutu da olabilir.
_NPM_RUN = re.compile(r"\bnpm\s+(?P<run>run-script\s+|run\s+)?(?P<script>[\w:.-]+)")
#: `run` olmadan yazılan npm alt komutları betik adı DEĞİLDİR (ölçüldü: `npm i`,
#: `npm audit`, `npm exec` "betik yok" bulgusu üretiyordu).
_NPM_SUBCOMMANDS = frozenset(
    [
        "i",
        "install",
        "add",
        "update",
        "up",
        "upgrade",
        "audit",
        "exec",
        "x",
        "pack",
        "publish",
        "link",
        "ln",
        "unlink",
        "rebuild",
        "rb",
        "uninstall",
        "remove",
        "rm",
        "un",
        "r",
        "outdated",
        "prune",
        "dedupe",
        "ddp",
        "ls",
        "list",
        "ll",
        "la",
        "config",
        "c",
        "cache",
        "whoami",
        "login",
        "logout",
        "adduser",
        "version",
        "view",
        "info",
        "show",
        "search",
        "find",
        "help",
        "init",
        "create",
        "explore",
        "doctor",
        "fund",
        "diff",
        "pkg",
        "prefix",
        "root",
        "bin",
        "set-script",
        "star",
        "unstar",
        "team",
        "token",
        "access",
        "owner",
        "deprecate",
        "dist-tag",
        "ping",
        "profile",
        "repo",
        "bugs",
        "docs",
        "home",
        "org",
        "shrinkwrap",
        "sbom",
        "query",
        "restart",
        "stop",
        "completion",
        "hook",
        "edit",
        "get",
        "set",
        "install-test",
        "it",
        "cit",
        "install-ci-test",
    ]
)


class ScriptPathVerifier:
    """`package.json` betiklerinin gösterdiği yollar ve betikler gerçekten var mı?"""

    def __init__(self, root: Path) -> None:
        self._root = root

    async def verify(self) -> VerificationResult:
        paket = self._root / "package.json"
        scripts = _load_scripts(paket)
        if not scripts:
            return VerificationResult(ok=True)

        bulgular: list[str] = []
        for ad, komut in scripts.items():
            bulgular.extend(_check(ad, komut, self._root))
        if not bulgular:
            return VerificationResult(ok=True)
        return VerificationResult(
            ok=False,
            summary=f"package.json betiklerinde {len(bulgular)} geçersiz yol/betik referansı",
            findings=tuple(bulgular),
        )


def _load_scripts(paket: Path) -> dict[str, str]:
    if not paket.is_file():
        return {}
    try:
        veri = json.loads(paket.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        # Bozuk package.json bu kapının sorunu değil; derleme kapısı onu söyler.
        return {}
    scripts = veri.get("scripts") if isinstance(veri, dict) else None
    if not isinstance(scripts, dict):
        return {}
    return {ad: komut for ad, komut in scripts.items() if isinstance(komut, str)}


def _check(ad: str, komut: str, root: Path) -> list[str]:
    """Tek bir betiğin gösterdiği hedefleri denetle.

    Komut `&&`/`;`/`|` ile parçalanır ve `cd` durumu sırayla taşınır: her `cd` yalnız
    kendinden sonraki parçaları (bir sonraki `cd`'ye dek) etkiler, göreli `cd`'ler
    önceki dizine göre çözülür. Ölçüldü (29 Ekim): `cd web && npm run build && cd ../api
    && npm run start:dev` içinde `start:dev` `web/`te aranıp yanlış bulgu veriyordu.
    """
    bulgular: list[str] = []
    for eslesme in _PREFIX_RUN.finditer(komut):
        bulgular.extend(_check_target(ad, root, eslesme.group("path"), eslesme.group("script")))
    mevcut: str | None = None
    for parca in _SEGMENT_SPLIT.split(komut):
        cd = _CD.search(parca)
        if cd is not None:
            mevcut = posixpath.normpath(posixpath.join(mevcut or ".", cd.group("path")))
            bulgular.extend(_check_target(ad, root, mevcut, None))
        if mevcut is None:
            continue
        # TÜM npm çağrıları denetlenir, yalnızca ilki değil: "npm install && npm
        # run dev" zincirinde ilk eşleşme `install` olur, atlanır ve asıl hatalı
        # olan `run dev` hiç görülmezdi (ölçüldü).
        for npm in _NPM_RUN.finditer(parca):
            betik = npm.group("script")
            if npm.group("run") is None and betik in _NPM_SUBCOMMANDS:
                continue
            bulgular.extend(_check_target(ad, root, mevcut, betik))
    return list(dict.fromkeys(bulgular))


def _check_target(ad: str, root: Path, ham_yol: str, betik: str | None) -> list[str]:
    """Hedef dizin ve (varsa) çağrılan betik gerçekten var mı?"""
    hedef = (root / ham_yol).resolve()
    if not hedef.is_dir():
        return [f"'{ad}' betiği olmayan bir dizini gösteriyor: {ham_yol}"]
    if betik in (None, "install", "ci", "test", "start"):
        # `npm install`/`ci` betik adı değildir; `test`/`start` npm'in yerleşik
        # varsayılanlarıdır ve package.json'da tanımlı olmayabilir.
        return []
    hedef_scripts = _load_scripts(hedef / "package.json")
    if not hedef_scripts:
        return [
            f"'{ad}' betiği {ham_yol} altında npm çalıştırıyor ama orada "
            "package.json yok — doğru alt dizini göster."
        ]
    if betik not in hedef_scripts:
        mevcut = ", ".join(sorted(hedef_scripts)[:6])
        return [
            f"'{ad}' betiği {ham_yol} içinde '{betik}' betiğini çağırıyor ama orada "
            f"böyle bir betik yok (var olanlar: {mevcut})."
        ]
    return []
