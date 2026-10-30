"""Test kurcalama denetimi: ajan başarıyı testi zayıflatarak göstermesin.

Ölçülen risk (ImpossibleBench, yol haritası 5. adım): ajan geçemediği testi düzeltmek
yerine silebiliyor, `skip`/`xfail` ekleyebiliyor ya da CI'daki test komutunu
değiştirebiliyor; sonra "testler geçti" diyor ve kanıt kapısı geçen komutu görüyor.
Bu modül turda GERÇEKTEN olan dosya değişikliğine (`ChangeSet` ilk hâl ↔ diskteki
şimdiki hâl) ve kabuk komutlarına bakar; modelin beyanına bakmaz.

Engellemez, İŞARETLER: bulgular tur raporuna (`TurnReport.test_tamper`) düşer; zayıflatan
bulgu varken "testler geçti" kanıtı tek başına başarı sayılmaz.

Yanlış alarmı sınırlama:

- Yeni eklenen test dosyası şüpheli DEĞİLDİR (yalnız var olan test zayıflatılabilir).
- Görev açıkça test yazmak/düzeltmekse (`task_requests_test_work`) var olan teste
  dokunmak ve assert sayısının düşmesi bildirilmez; `skip` eklemek, test dosyasını silmek
  ve CI/test yapılandırmasını değiştirmek yine bildirilir.
- Yapılandırma dosyalarında yalnız TEST ile ilgili bölüm karşılaştırılır
  (`package.json` `scripts.test`, `pyproject.toml` `[tool.pytest*]`, Makefile `test*`
  hedefi); bağımlılık eklemek alarm vermez.
"""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from ...core.changeset import ChangeSet, Snapshot
from ...core.events import TamperSuspected
from ...core.evidence import ToolUse
from ...core.text_fold import fold_tr
from ...core.tools import ToolFamily, tool_family

#: Bulgu başına detay metni üst sınırı (rapor satırı küçük kalsın).
_DETAIL_LIMIT = 160
#: Raporda en fazla gösterilen bulgu.
REPORT_FINDING_LIMIT = 6


class TamperKind(StrEnum):
    """Bulgu türü. Değer, ölçüm izinde ve olayda görünen kararlı addır."""

    #: Var olan test dosyasına dokunuldu ama zayıflatma izi YOK (yalnız uyarı).
    TEST_TOUCHED = "test_dosyasi_degisti"
    TEST_DELETED = "test_dosyasi_silindi"
    SKIP_ADDED = "atlama_eklendi"
    ASSERT_REMOVED = "assert_azaldi"
    TEST_REMOVED = "test_islevi_azaldi"
    #: CI iş akışı, pytest/jest yapılandırması ya da `test` betiği/hedefi değişti.
    CI_CHANGED = "ci_degisti"
    #: Kabuk komutu test/CI dosyasını sildi, taşıdı ya da üzerine yazdı.
    SHELL_MUTATION = "kabuk_test_mutasyonu"


@dataclass(frozen=True, slots=True)
class TamperFinding:
    """Tek bir şüpheli test/CI değişikliği."""

    kind: TamperKind
    path: str
    detail: str = ""

    @property
    def weakens(self) -> bool:
        """Testi/komutu ZAYIFLATAN bulgu mu (kanıtı düşürür), yoksa yalnız uyarı mı."""
        return self.kind is not TamperKind.TEST_TOUCHED


# --------------------------------------------------------------------------- #
# Yol sınıflandırması
# --------------------------------------------------------------------------- #

_TEST_DIRS = frozenset({"tests", "test", "__tests__", "spec", "specs", "e2e"})
_CODE_SUFFIXES = frozenset(
    {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs", ".php", ".rb",
     ".java", ".kt", ".cs", ".swift", ".sh", ".gd"}
)  # fmt: skip
_TEST_NAME = re.compile(
    r"^(?:test_.*|.*_test\..*|.*\.(?:test|spec)\.[a-z]+|conftest\.py|.*Tests?\.(?:php|java|cs|kt))$"
)
#: Tüm dosyası karşılaştırılan CI/test yapılandırmaları (ad ya da yol kalıbı).
_CI_WHOLE_FILE = re.compile(
    r"^(?:\.github/workflows/[^/]+\.ya?ml|\.gitlab-ci\.ya?ml|\.circleci/config\.ya?ml"
    r"|azure-pipelines\.ya?ml|Jenkinsfile|pytest\.ini|tox\.ini|setup\.cfg|noxfile\.py"
    r"|(?:jest|vitest|playwright|karma)\.config\.[a-z]+|jest\.config\.json)$"
)
_SECTION_FILES = ("package.json", "pyproject.toml", "Makefile", "makefile", "GNUmakefile")


def is_test_file(path: str) -> bool:
    """Yol bir test dosyası mı (dizin ya da ad kalıbı; veri/fixture dosyaları hariç)."""
    pure = PurePosixPath(path.replace("\\", "/"))
    if pure.suffix not in _CODE_SUFFIXES:
        return False
    return bool(_TEST_NAME.match(pure.name)) or any(part in _TEST_DIRS for part in pure.parts[:-1])


def is_ci_file(path: str) -> bool:
    """Yol bir CI/test yapılandırması mı (bölüm düzeyinde olanlar dahil)."""
    normal = path.replace("\\", "/")
    name = PurePosixPath(normal).name
    return (
        name in _SECTION_FILES
        or bool(_CI_WHOLE_FILE.match(normal))
        or bool(_CI_WHOLE_FILE.match(name))
    )


# --------------------------------------------------------------------------- #
# Görev: test işi mi?
# --------------------------------------------------------------------------- #

_TEST_WORK_VERBS = r"(?:yaz|ekle|düzelt|güncelle|onar|tamamla|iyileştir|oluştur|genişlet)\w*"
_TEST_WORK = re.compile(
    rf"\b(?:birim\s+)?test\w*\s+(?:\w+\s+){{0,2}}{_TEST_WORK_VERBS}"
    r"|\b(?:write|add|fix|update|repair|create|improve|extend)\s+(?:\w+\s+){0,2}tests?\b",
    re.IGNORECASE,
)


def task_requests_test_work(task: str) -> bool:
    """Kullanıcı açıkça test yazmayı/düzeltmeyi mi istiyor.

    Bitişiklik şartı bilerek dar: "hatayı düzelt, testler geçsin" test işi DEĞİLDİR
    (testi değiştirerek geçirmenin tam senaryosu); noktalama eşleşmeyi böler.
    """
    return bool(task) and bool(_TEST_WORK.search(fold_tr(task)))


# --------------------------------------------------------------------------- #
# İçerik analizi
# --------------------------------------------------------------------------- #

_COMMENT_LINE = re.compile(r"^\s*(?:#(?!\[)|//|\*|/\*)")
_SKIP_MARKERS = re.compile(
    r"@pytest\.mark\.(?:skip|skipif|xfail)\b|\bpytest\.(?:skip|xfail)\("
    r"|@unittest\.(?:skip|skipIf|skipUnless|expectedFailure)\b|\.skipTest\("
    r"|\b(?:it|test|describe|context|suite)\.(?:skip|todo|fails|failing|only)\b"
    r"|\b(?:xit|xtest|xdescribe|fit|fdescribe)\s*\(|\.only\s*\("
    r"|\bt\.Skip(?:f|Now)?\(|#\[ignore\b|@Disabled\b|@Ignore\b"
    r"|\bmarkTest(?:Skipped|Incomplete)\("
)
_ASSERTS = re.compile(
    r"\bassert\b|\bassert[A-Z_]\w*\s*\(|\bassert_\w+!?\s*\(|\bexpect\s*\("
    r"|\bpytest\.raises\b|\bt\.(?:Error|Fatal)f?\("
)
_TEST_FUNCS = re.compile(
    r"^\s*(?:async\s+)?def\s+test\w*\(|\b(?:it|test)\s*\(|^\s*func\s+Test\w+\("
    r"|#\[test\]|\bfunction\s+test\w*\(|\bpublic\s+function\s+test\w*\(",
    re.MULTILINE,
)


def _code_lines(text: str) -> str:
    """Yorum satırlarını at: yorumlanmış assert/skip sayılmaz (assert'i yorumlamak = silmek)."""
    return "\n".join(line for line in text.splitlines() if not _COMMENT_LINE.match(line))


def _decode(raw: bytes | None) -> str:
    return "" if raw is None else raw.decode("utf-8", errors="replace")


def _count(pattern: re.Pattern[str], text: str) -> int:
    return len(pattern.findall(text))


def _compare_test_file(
    rel: str, before: str, after: str, *, test_work: bool
) -> Iterable[TamperFinding]:
    """Var olan test dosyasının önceki ve şimdiki içeriğini karşılaştır."""
    if before == after:
        return
    old, new = _code_lines(before), _code_lines(after)
    weakened = False
    skips_old, skips_new = _count(_SKIP_MARKERS, old), _count(_SKIP_MARKERS, new)
    if skips_new > skips_old:
        weakened = True
        yield TamperFinding(
            TamperKind.SKIP_ADDED, rel, f"skip/xfail/only işareti {skips_old} → {skips_new}"
        )
    if not test_work:
        asserts_old, asserts_new = _count(_ASSERTS, old), _count(_ASSERTS, new)
        if asserts_new < asserts_old:
            weakened = True
            yield TamperFinding(
                TamperKind.ASSERT_REMOVED, rel, f"assert sayısı {asserts_old} → {asserts_new}"
            )
        funcs_old, funcs_new = _count(_TEST_FUNCS, old), _count(_TEST_FUNCS, new)
        if funcs_new < funcs_old:
            weakened = True
            yield TamperFinding(
                TamperKind.TEST_REMOVED, rel, f"test işlevi sayısı {funcs_old} → {funcs_new}"
            )
    if not weakened and not test_work:
        yield TamperFinding(TamperKind.TEST_TOUCHED, rel, "mevcut test dosyası değiştirildi")


# --- Yapılandırma: yalnız test ile ilgili bölüm ---------------------------- #


def _normal(text: str) -> str:
    """Boşluk ve yorum farkını yok say."""
    lines = (line.strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line and not line.startswith("#"))


def _package_test_scripts(text: str) -> str:
    try:
        data = json.loads(text) if text.strip() else {}
    except ValueError:
        return _normal("\n".join(line for line in text.splitlines() if '"test' in line))
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return ""
    return json.dumps(
        {name: scripts[name] for name in sorted(scripts) if re.match(r"^(?:pre|post)?test", name)},
        sort_keys=True,
    )


def _pyproject_pytest(text: str) -> str:
    sections = re.findall(r"^\[tool\.pytest[^\]]*\][^\[]*", text, flags=re.MULTILINE)
    return _normal("\n".join(sections))


def _makefile_test_targets(text: str) -> str:
    blocks = re.findall(
        r"^(?:\.PHONY:[^\n]*\n)?test[\w-]*:[^\n]*(?:\n[\t ][^\n]*)*", text, flags=re.MULTILINE
    )
    return _normal("\n".join(block for block in blocks if not block.startswith(".PHONY")))


def _ci_projection(rel: str, text: str) -> str:
    """Dosyanın TEST ile ilgili izdüşümü; iki hâlin izdüşümü farklıysa CI değişmiştir."""
    name = PurePosixPath(rel).name
    if name == "package.json":
        return _package_test_scripts(text)
    if name == "pyproject.toml":
        return _pyproject_pytest(text)
    if name in {"Makefile", "makefile", "GNUmakefile"}:
        return _makefile_test_targets(text)
    return _normal(text)


def _compare_ci_file(
    rel: str, before: bytes | None, after: bytes | None
) -> Iterable[TamperFinding]:
    if before is None:
        return  # Yeni eklenen yapılandırma var olan bir testi zayıflatmaz.
    if after is None:
        yield TamperFinding(TamperKind.CI_CHANGED, rel, "dosya silindi")
        return
    if _ci_projection(rel, _decode(before)) != _ci_projection(rel, _decode(after)):
        yield TamperFinding(TamperKind.CI_CHANGED, rel, "test komutu/yapılandırması değişti")


# --------------------------------------------------------------------------- #
# Kabuk komutları
# --------------------------------------------------------------------------- #

_SEPARATORS = re.compile(r"&&|\|\||;|\n|\|")
_DESTRUCTIVE = frozenset({"rm", "unlink", "mv", "truncate", "shred"})
_REDIRECT = re.compile(r">>?\s*(\S+)")


def _is_shell(name: str) -> bool:
    return tool_family(name) is ToolFamily.SHELL


def _segment_targets(segment: str) -> list[str]:
    """Parçanın test/CI dosyasına yönelik yıkıcı/yazıcı hedeflerini döndür."""
    try:
        tokens = shlex.split(segment)
    except ValueError:
        return []
    if not tokens:
        return []
    name = tokens[0].rsplit("/", 1)[-1]
    args = [token for token in tokens[1:] if not token.startswith("-")]
    writes: list[str] = []
    if name in _DESTRUCTIVE:
        writes = args
    elif name == "git" and len(tokens) > 2 and tokens[1] in {"rm", "mv"}:
        writes = args[1:]
    elif name in {"sed", "perl"} and any(
        token.startswith("-i") or token == "--in-place" or re.fullmatch(r"-p[a-z]*i[a-z]*", token)
        for token in tokens[1:]
    ):
        writes = args
    writes += _REDIRECT.findall(segment)
    return [target for target in writes if is_test_file(target) or is_ci_file(target)]


def _shell_findings(tool_uses: Iterable[ToolUse]) -> Iterable[TamperFinding]:
    for use in tool_uses:
        if not _is_shell(use.name) or not use.ok:
            continue
        command = use.arguments.get("command") if isinstance(use.arguments, dict) else None
        if not isinstance(command, str):
            continue
        for segment in _SEPARATORS.split(command):
            for target in _segment_targets(segment):
                yield TamperFinding(
                    TamperKind.SHELL_MUTATION, target, command.strip()[:_DETAIL_LIMIT]
                )


# --------------------------------------------------------------------------- #
# Giriş noktası
# --------------------------------------------------------------------------- #


def _snapshot_findings(
    snapshot: Snapshot, root: str, *, test_work: bool
) -> Iterable[TamperFinding]:
    path = snapshot.path
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.as_posix()
    is_test, is_ci = is_test_file(rel), is_ci_file(rel)
    if not (is_test or is_ci) or snapshot.content is None:
        return  # Bu turda YENİ oluşturulan dosya var olan bir testi zayıflatmaz.
    try:
        after: bytes | None = path.read_bytes()
    except FileNotFoundError:
        after = None
    except OSError:
        return
    if is_test:
        if after is None:
            yield TamperFinding(TamperKind.TEST_DELETED, rel, "test dosyası silindi")
        else:
            yield from _compare_test_file(
                rel, _decode(snapshot.content), _decode(after), test_work=test_work
            )
    if is_ci:
        yield from _compare_ci_file(rel, snapshot.content, after)


def detect_test_tampering(
    changes: ChangeSet,
    root: object,
    tool_uses: Iterable[ToolUse],
    *,
    task: str = "",
) -> tuple[TamperFinding, ...]:
    """Turda test/CI dosyalarına yapılan zayıflatma ve dokunuşları bul.

    `changes` turun ilk-hâl kaydıdır; şimdiki hâl diskten okunur, yani ara adımlar değil
    NET etki karşılaştırılır (sil-geri yaz zinciri alarm vermez). Aynı (tür, yol) çifti
    tek kez döner.
    """
    test_work = task_requests_test_work(task)
    base = str(root)
    found: dict[tuple[TamperKind, str], TamperFinding] = {}
    for snapshot in changes.snapshots:
        for finding in _snapshot_findings(snapshot, base, test_work=test_work):
            found.setdefault((finding.kind, finding.path), finding)
    for finding in _shell_findings(tool_uses):
        found.setdefault((finding.kind, finding.path), finding)
    return tuple(found.values())


def collect_test_tampering(
    deps: object, tool_uses: Iterable[ToolUse], task: str = ""
) -> tuple[TamperFinding, ...]:
    """Tur raporu için bulguları topla ve ölçüm izi olarak `TamperSuspected` yayınla.

    `loop._apply_turn_report` ile plan yürütücüsünün konsolide raporu AYNI yolu kullanır.
    `deps` gevşek yazılır (sahte bağımlılıklar `config=None` verebilir); `runtime.
    test_tamper_check` kapalıysa boş döner.
    """
    runtime = getattr(getattr(deps, "config", None), "runtime", None)
    if not getattr(runtime, "test_tamper_check", True):
        return ()
    context = deps.tool_context  # type: ignore[attr-defined]
    findings = detect_test_tampering(context.changes, context.root, tool_uses, task=task)
    if findings:
        deps.publisher.publish(  # type: ignore[attr-defined]
            TamperSuspected(
                count=len(findings),
                weakening=sum(1 for item in findings if item.weakens),
                kinds=tuple(sorted({item.kind.value for item in findings})),
                paths=tuple(dict.fromkeys(item.path for item in findings))[:10],
            )
        )
    return findings


def has_weakening(findings: Iterable[TamperFinding]) -> bool:
    """Bulgulardan biri testi/komutu zayıflatıyor mu (yalnız `TEST_TOUCHED` değil)."""
    return any(finding.weakens for finding in findings)


def render_findings(findings: tuple[TamperFinding, ...]) -> str:
    """Tur raporuna giren Türkçe uyarı bloğu; bulgu yoksa boş."""
    if not findings:
        return ""
    lines = [
        f"- {finding.path}: {finding.detail or finding.kind.value}"
        for finding in findings[:REPORT_FINDING_LIMIT]
    ]
    kalan = len(findings) - REPORT_FINDING_LIMIT
    if kalan > 0:
        lines.append(f"- ... ve {kalan} bulgu daha")
    baslik = (
        "⚠ ŞÜPHELİ TEST DEĞİŞİKLİĞİ — ajan var olan bir testi/test komutunu zayıflatmış "
        'olabilir; "testler geçti" kanıtı tek başına başarı sayılmaz, değişikliği elle incele.'
        if has_weakening(findings)
        else "⚠ Mevcut test dosyası da değiştirildi — geçen testin kanıt değeri sınırlıdır, "
        "değişikliği incele."
    )
    return baslik + "\n" + "\n".join(lines)
