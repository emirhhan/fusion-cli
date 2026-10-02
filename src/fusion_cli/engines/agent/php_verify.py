"""PHP ve WordPress teması doğrulama kapısı.

Ölçüldü (30 Eylül, WordPress sohbeti): ajan iki dosyada PHP sözdizimi hatası
bıraktı, `functions.php` var olmayan `js/navigation.js`'e, `index.php` var olmayan
`template-parts/content*.php`'ye başvurdu ve tur "hazır" dedi. Doğrulama kapısı
JS/HTML/CSS'i denetliyordu, PHP'yi değil. Bu kapı iki şeye bakar:

1. **Sözdizimi** — dokunulan her `.php` için `php -l`. PHP kurulu değilse
   ENGELLEMEZ ama "doğrulanamadı" uyarısı verir: kullanıcıya "doğrulandı"
   denmesin.
2. **WordPress tema başvuruları** — `get_template_part('a/b', 'c')`,
   `get_template_directory_uri() . '/x/y.js'`, `get_template_directory() . '/inc/z.php'`
   ile anılan dosya temada YOKSA engelleyici bulgu.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

from ...core.constants import PHP_LINT_TIMEOUT_S
from ...core.evidence import CriterionEvidence, EvidenceStatus
from ...core.execution_plan import VerificationCheckKind
from ...core.tools import ToolContext
from ...core.verification import VerificationResult

#: Homebrew/sistem PHP'si uygulama PATH'inde olmayabilir (masaüstü uygulaması
#: kabuk profilini okumaz); bilinen yerlere de bakılır.
_PHP_CANDIDATES = ("/opt/homebrew/bin/php", "/usr/local/bin/php", "/usr/bin/php")

_THEME_URI = re.compile(
    r"get_(?:template|stylesheet)_directory(?:_uri)?\(\)\s*\.\s*['\"]/?([^'\"$]+)['\"]"
)
#: `wc_get_template_part` HARİÇ: WooCommerce eklenti şablonlarına düşebilir.
_TEMPLATE_PART = re.compile(
    r"(?<![\w])get_template_part\(\s*['\"]([^'\"$]+)['\"]\s*(?:,\s*['\"]([^'\"$]*)['\"])?"
)


def _existing_php(paths: tuple[Path, ...]) -> list[Path]:
    return sorted(p for p in paths if p.suffix.lower() == ".php" and p.is_file())


def find_php_executable() -> str | None:
    found = shutil.which("php")
    if found:
        return found
    return next((path for path in _PHP_CANDIDATES if Path(path).is_file()), None)


class PhpVerifier:
    """Dokunulan PHP dosyalarını ve WordPress tema başvurularını denetler."""

    def __init__(self, context: ToolContext, php: str | None) -> None:
        self._context = context
        self._php = php

    async def verify(self) -> VerificationResult:
        files = await asyncio.to_thread(_existing_php, tuple(self._context.touched))
        if not files:
            return VerificationResult(ok=True)
        findings: list[str] = []
        warnings: list[str] = []
        if self._php is None:
            warnings.append(
                "PHP kurulu değil: .php sözdizimi DOĞRULANAMADI. Kullanıcıya 'doğrulandı' "
                "deme; PHP kurulunca `php -l` ile denetlenmeli."
            )
        else:
            for path in files:
                error = await _lint(self._php, path)
                if error:
                    findings.append(f"{self._label(path)} PHP sözdizimi hatası:\n{error}")
        for path in files:
            findings.extend(
                await asyncio.to_thread(missing_theme_references, path, self._context.root)
            )
        if not findings:
            # `php -l` gerçekten çalıştıysa bu bir doğrulama KANITIDIR: rapor "doğrulama
            # çalıştırılmadı" demesin (bkz. `turn_report._gate_passed_evidence`).
            kanit = (
                (
                    CriterionEvidence(
                        criterion_id="php_sozdizimi",
                        kind=VerificationCheckKind.COMMAND,
                        status=EvidenceStatus.PASSED,
                        summary=f"php -l {len(files)} dosyada temiz, tema başvuruları mevcut",
                        command="php -l",
                    ),
                )
                if self._php is not None
                else ()
            )
            return VerificationResult(ok=True, warnings=tuple(warnings), evidence=kanit)
        return VerificationResult(
            ok=False,
            summary=f"PHP denetiminde {len(findings)} engelleyici sorun",
            findings=tuple(findings),
            warnings=tuple(warnings),
        )

    def _label(self, path: Path) -> str:
        try:
            return path.relative_to(self._context.root).as_posix()
        except ValueError:
            return str(path)


async def _lint(php: str, path: Path) -> str:
    """`php -l` hatası; temizse boş metin."""
    try:
        process = await asyncio.create_subprocess_exec(
            php,
            "-l",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await asyncio.wait_for(process.communicate(), timeout=PHP_LINT_TIMEOUT_S)
    except TimeoutError:
        process.kill()
        return f"`php -l` {PHP_LINT_TIMEOUT_S:g} sn'de bitmedi"
    except OSError as error:
        return f"`php -l` çalıştırılamadı: {error}"
    if process.returncode == 0:
        return ""
    return output.decode("utf-8", errors="replace").strip()[-1500:]


def theme_root(path: Path) -> Path | None:
    """Dosyanın bağlı olduğu WordPress teması (`Theme Name:` taşıyan style.css)."""
    for folder in path.parents:
        style = folder / "style.css"
        try:
            if style.is_file() and "Theme Name:" in style.read_text(encoding="utf-8")[:2000]:
                return folder
        except OSError:
            continue
    return None


def missing_theme_references(path: Path, root: Path) -> list[str]:
    """Tema dosyasının andığı ama temada olmayan dosyalar."""
    theme = theme_root(path)
    if theme is None:
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []
    source = _strip_comments(source)
    label = path.relative_to(theme).as_posix()
    findings: list[str] = []
    for match in _THEME_URI.finditer(source):
        relative = match.group(1).split("?")[0]
        # Uzantısız başvuru klasördür (`/languages`): yokluğu WordPress'te hata değil.
        if relative and Path(relative).suffix and not (theme / relative).exists():
            findings.append(f"{label} temada olmayan dosyaya başvuruyor: {relative}")
    for match in _TEMPLATE_PART.finditer(source):
        slug, name = match.group(1), match.group(2)
        candidates = [f"{slug}-{name}.php"] if name else []
        candidates.append(f"{slug}.php")
        if not any((theme / candidate).is_file() for candidate in candidates):
            findings.append(
                f"{label} get_template_part ile olmayan şablonu çağırıyor: {' / '.join(candidates)}"
            )
    return findings


_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_comments(source: str) -> str:
    """Yorumdaki başvurular denetlenmez (`// wp_enqueue_style(...)`)."""
    without_blocks = _BLOCK_COMMENT.sub("", source)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith(("//", "#"))
    )
