"""`plugin validate <yol> [--strict] [--json]` — Claude Code sözleşmesi (#412).

Claude Code (https://code.claude.com/docs/en/plugins/cli-reference.md "plugin validate"):
- Yol bir bildirim dosyası ya da klasördür. Klasörde önce `.claude-plugin/marketplace.json`
  (varsa yanındaki `plugin.json` da), yoksa `.claude-plugin/plugin.json` doğrulanır.
- Karar satırı ve çıkış kodu: `Validation passed` / `passed with warnings` → 0; `failed` (ya da
  `--strict` altında uyarı) → 1; doğrulayıcının kendisi çökerse (okunamayan yol) → 2, stdout boş.
- Uyarılar: eksik version/description/author, kebab-case dışı ad, kökteki CLAUDE.md.
- `--json`: `success`, `strict`, `target`, `manifest`, `contents` (`file`, `errors`, `warnings`,
  `notes`) ve `advice` alanları.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..core.plugin_marketplace import parse_marketplace
from ..core.plugins import PluginError
from .plugin_layout import ERR_NO_COMPONENTS, validate_plugin

MARKETPLACE_FILE = Path(".claude-plugin") / "marketplace.json"
PLUGIN_FILE = Path(".claude-plugin") / "plugin.json"

PASSED = "Doğrulama başarılı"
PASSED_WARNINGS = "Doğrulama uyarılarla başarılı"
FAILED = "Doğrulama başarısız"
FAILED_STRICT = "Doğrulama başarısız (--strict uyarıları hata sayar)"
UNEXPECTED = "Doğrulama sırasında beklenmeyen hata: {reason}"
HEAD_MARKET = "Pazar bildirimi doğrulanıyor: {path}"
HEAD_PLUGIN = "Eklenti bildirimi doğrulanıyor: {path}"
ERR_NO_TARGET = "doğrulanacak bildirim yok (.claude-plugin/marketplace.json ya da plugin.json)"
WARN_VERSION = "version alanı yok"
WARN_DESCRIPTION = "description alanı yok"
WARN_AUTHOR = "author alanı yok"
WARN_CLAUDE_MD = "eklenti kökünde CLAUDE.md var; Claude Code eklentiden CLAUDE.md yüklemez"


class ValidationCrashError(PluginError):
    """Doğrulayıcının kendisi başarısız (çıkış 2)."""


@dataclass(frozen=True, slots=True)
class FileResult:
    file: str
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def payload(self) -> dict[str, object]:
        return {
            "file": self.file,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class ValidationRun:
    target: Path
    is_marketplace: bool
    manifest: FileResult
    contents: tuple[FileResult, ...]
    strict: bool

    @property
    def _all(self) -> tuple[FileResult, ...]:
        return (self.manifest, *self.contents)

    @property
    def has_errors(self) -> bool:
        return any(item.errors for item in self._all)

    @property
    def has_warnings(self) -> bool:
        return any(item.warnings for item in self._all)

    @property
    def success(self) -> bool:
        return not self.has_errors and not (self.strict and self.has_warnings)

    @property
    def exit_code(self) -> int:
        return 0 if self.success else 1

    def verdict(self) -> str:
        if self.success:
            return PASSED_WARNINGS if self.has_warnings else PASSED
        return FAILED if self.has_errors else FAILED_STRICT

    def payload(self) -> dict[str, object]:
        reported = [item.payload() for item in self.contents if item.errors or item.warnings]
        return {
            "success": self.success,
            "strict": self.strict,
            "target": str(self.target),
            "manifest": self.manifest.payload(),
            "contents": reported,
            "advice": [],
        }

    def text(self) -> str:
        head = HEAD_MARKET if self.is_marketplace else HEAD_PLUGIN
        lines = [head.format(path=self.target)]
        for item in self._all:
            lines.extend(f"  ✘ {item.file}: {error}" for error in item.errors)
            lines.extend(f"  ⚠ {item.file}: {warning}" for warning in item.warnings)
        mark = "✔" if self.success else "✘"
        return "\n".join([*lines, f"{mark} {self.verdict()}"])


def _resolve(path: Path) -> tuple[Path, bool]:
    """(bildirim dosyası, pazar mı?); yol yoksa ya da okunamıyorsa `ValidationCrashError`."""
    if not path.exists():
        raise ValidationCrashError(UNEXPECTED.format(reason=f"yol yok: {path}"))
    if path.is_file():
        return path, path.name == MARKETPLACE_FILE.name
    for relative, market in ((MARKETPLACE_FILE, True), (PLUGIN_FILE, False)):
        if (path / relative).is_file():
            return path / relative, market
    return path / PLUGIN_FILE, False


def _marketplace(file: Path) -> FileResult:
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValidationCrashError(UNEXPECTED.format(reason=error)) from error
    except ValueError as error:
        return FileResult(str(file), (f"JSON okunamadı: {error}",))
    try:
        market = parse_marketplace(raw, where=file.name)
    except PluginError as error:
        return FileResult(str(file), (str(error),))
    return FileResult(str(file), warnings=market.warnings)


def _plugin(root: Path, file: Path) -> FileResult:
    report = validate_plugin(root)
    if report.layout is None and not file.is_file() and not root.is_dir():
        raise ValidationCrashError(UNEXPECTED.format(reason=f"okunamadı: {root}"))
    errors = [e for e in report.errors if e != ERR_NO_COMPONENTS]
    warnings = list(report.warnings)
    if not file.is_file():
        errors.insert(0, ERR_NO_TARGET)
    if report.layout is not None and file.is_file():
        manifest = report.layout.manifest
        missing = (
            (manifest.version, WARN_VERSION),
            (manifest.description, WARN_DESCRIPTION),
            (manifest.author, WARN_AUTHOR),
        )
        warnings.extend(text for value, text in missing if not value)
    if (root / "CLAUDE.md").is_file():
        warnings.append(WARN_CLAUDE_MD)
    return FileResult(str(file), tuple(errors), tuple(warnings))


def validate_target(path: Path, *, strict: bool = False) -> ValidationRun:
    """Claude `plugin validate` sırası: pazar → (yanındaki) eklenti → bileşenler."""
    file, is_market = _resolve(path)
    root = file.parent.parent if file.parent.name == ".claude-plugin" else file.parent
    if is_market:
        contents: tuple[FileResult, ...] = ()
        if (root / PLUGIN_FILE).is_file():
            contents = (_plugin(root, root / PLUGIN_FILE),)
        return ValidationRun(file, True, _marketplace(file), contents, strict)
    return ValidationRun(file, False, _plugin(root, file), (), strict)
