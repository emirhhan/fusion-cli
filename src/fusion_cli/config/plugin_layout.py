"""Eklenti klasörünü tarama, doğrulama ve içerik karması (P-059).

`scan_plugin` bildirimi okur ve bileşen dosyalarını bulur; `validate_plugin` aynı taramanın
üstüne kanca/MCP dosyalarını ayrıştırıp hata/uyarı listesi çıkarır (`fusion eklenti dogrula`,
Claude Code `claude plugin validate`). `tree_digest` klasörün içerik karmasıdır: kurulumda
kaydedilir, yüklemede yeniden hesaplanır; dosyalar sonradan değiştiyse eklenti yüklenmez.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..core.errors import ConfigError
from ..core.plugins import (
    MANIFEST_PATHS,
    ROOT_VARIABLES,
    PluginError,
    PluginManifest,
    parse_manifest,
    substitute_root,
)
from ..core.redaction import redact
from .mcp_json import parse_project_mcp
from .models import McpScope, McpServerConfig

#: Karma ve doğrulamada dosya sınırları: dev bir depo "eklenti" diye kurulmasın.
MAX_PLUGIN_FILES = 5_000
MAX_PLUGIN_BYTES = 50 * 1024 * 1024
#: Karmada atlanan dizinler: git iç verisi ve Python önbelleği (kurulumda kod çalışmaz;
#: `node_modules` gibi çalıştırılabilir içerik karmaya DAHİLDİR).
_SKIP_DIRS = frozenset({".git", "__pycache__"})
#: Bağlam maliyeti tahmini: dizine giren her satır için karakter/4 ≈ token.
CHARS_PER_TOKEN = 4
#: Eklenti MCP sunucusunun Fusion'daki adı: `plugin_<eklenti>_<sunucu>` (araç adına uygun).
_SERVER_SLUG = re.compile(r"[^A-Za-z0-9]+")
_FRONTMATTER = re.compile(r"\A\s*---\n(.*?)\n---", re.DOTALL)

ERR_TOO_BIG = "eklenti çok büyük: en çok {files} dosya / {mb} MB"
ERR_NO_COMPONENTS = "eklentide hiçbir bileşen yok (skills/, commands/, agents/, hooks, .mcp.json)"
ERR_HOOKS = "{path}: kanca dosyası geçersiz: {error}"
ERR_MCP = "{path}: MCP tanımı geçersiz: {error}"
WARN_MCP_SKIPPED = (
    "{path}: '{server}' MCP sunucusu atlandı ({error}); eklentinin geri kalanı kurulur"
)
WARN_NO_DESCRIPTION = "{path}: açıklama (description) yok; model ne zaman kullanacağını bilemez"
WARN_NO_MANIFEST = "plugin.json yok; ad klasörden alındı ({name})"


@dataclass(frozen=True, slots=True)
class PluginLayout:
    """Diskteki bir eklentinin bileşenleri."""

    root: Path
    manifest: PluginManifest
    has_manifest: bool
    skills: tuple[Path, ...] = ()
    #: `(komut adı, dosya)`; ad alt klasörlerle `a:b` biçimindedir (önek hariç).
    commands: tuple[tuple[str, Path], ...] = ()
    agents: tuple[Path, ...] = ()
    output_styles: tuple[Path, ...] = ()
    hook_files: tuple[Path, ...] = ()
    mcp_files: tuple[Path, ...] = ()

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def has_hooks(self) -> bool:
        return bool(self.hook_files or self.manifest.inline_hooks)

    @property
    def has_mcp(self) -> bool:
        return bool(self.mcp_files or self.manifest.inline_mcp)

    @property
    def is_executable(self) -> bool:
        """Kanca ya da MCP: Fusion'ın dışında süreç başlatır → kurulumda açık onay ister."""
        return self.has_hooks or self.has_mcp


@dataclass(frozen=True, slots=True)
class ValidationReport:
    layout: PluginLayout | None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    servers: tuple[McpServerConfig, ...] = field(default=())
    hook_count: int = 0
    #: Onay ekranında gösterilen kanca satırları: `Olay [eşleşen]: komut`.
    #
    # Ölçüldü (31 Ekim): onay ekranları yalnız "3 kanca" sayısını ve MCP'nin ilk sözcüğünü
    # (`bash -c 'curl … | sh'` → `bash`) gösteriyordu; kullanıcı neyi onayladığını göremiyordu.
    hook_lines: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.layout is not None and not self.errors


def read_manifest(root: Path) -> tuple[PluginManifest, bool]:
    """Bildirim ve var olup olmadığı. Bozuk bildirim `PluginError`."""
    for relative in MANIFEST_PATHS:
        path = root / relative
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise PluginError(f"{relative}: okunamadı: {error}") from error
            return parse_manifest(raw, fallback_name=root.name.lower(), where=relative), True
    return parse_manifest(None, fallback_name=root.name.lower()), False


def scan_plugin(root: Path) -> PluginLayout:
    manifest, has_manifest = read_manifest(root)
    skills = tuple(
        path
        for base in _dirs(root, manifest.skills)
        for path in sorted(base.rglob("SKILL.md"))
        if _inside(path, root)
    )
    commands = tuple(
        (":".join(path.relative_to(base).with_suffix("").parts), path)
        for base in _dirs(root, manifest.commands)
        for path in sorted(base.rglob("*.md"))
        if _inside(path, root)
    )
    agents = tuple(
        path
        for base in _dirs(root, manifest.agents)
        for path in sorted(base.glob("*.md"))
        if _inside(path, root)
    )
    styles = tuple(
        path
        for base in _dirs(root, manifest.output_styles)
        for path in sorted(base.glob("*.md"))
        if _inside(path, root)
    )
    return PluginLayout(
        root,
        manifest,
        has_manifest,
        skills,
        commands,
        agents,
        styles,
        tuple(
            p for p in (root / rel for rel in manifest.hooks) if p.is_file() and _inside(p, root)
        ),
        tuple(
            p
            for p in (root / rel for rel in manifest.mcp_servers)
            if p.is_file() and _inside(p, root)
        ),
    )


def _dirs(root: Path, relatives: tuple[str, ...]) -> tuple[Path, ...]:
    return tuple(p for p in (root / rel for rel in relatives) if p.is_dir() and _inside(p, root))


def _inside(path: Path, root: Path) -> bool:
    """Sembolik bağ eklenti kökü dışına (`~/.ssh`) çıkmıyor mu?"""
    try:
        return path.resolve().is_relative_to(root.resolve())
    except OSError:
        return False


def validate_plugin(root: Path) -> ValidationReport:
    """Kurulmadan önce/sonra denetim: hata varsa kurulum yapılmaz."""
    try:
        layout = scan_plugin(root)
    except PluginError as error:
        return ValidationReport(None, (str(error),))
    errors: list[str] = []
    warnings = list(layout.manifest.warnings)
    if not layout.has_manifest:
        warnings.append(WARN_NO_MANIFEST.format(name=layout.name))
    try:
        tree_digest(root)
    except PluginError as error:
        errors.append(str(error))
    if not (layout.skills or layout.commands or layout.agents or layout.output_styles) and not (
        layout.is_executable
    ):
        errors.append(ERR_NO_COMPONENTS)
    for path in (*layout.skills, *layout.agents):
        if "description:" not in _frontmatter(path):
            warnings.append(WARN_NO_DESCRIPTION.format(path=path.relative_to(root)))
    hook_count = 0
    lines: tuple[str, ...] = ()
    try:
        blocks = hook_blocks(layout)
        hook_count = sum(_count_hooks(block) for _path, block in blocks)
        lines = tuple(
            _display(line, layout.root) for _p, block in blocks for line in _hook_lines(block)
        )
    except PluginError as error:
        errors.append(str(error))
    servers: tuple[McpServerConfig, ...] = ()
    try:
        servers, skipped = _mcp_servers(layout)
        warnings.extend(skipped)
    except PluginError as error:
        errors.append(str(error))
    return ValidationReport(layout, tuple(errors), tuple(warnings), servers, hook_count, lines)


def _display(text: str, root: Path) -> str:
    """Onay ekranı metni: kurulum yolu yerine kök değişkeni, sırlar maskeli."""
    return redact(text.replace(str(root), ROOT_VARIABLES[0]))


def server_target(server: McpServerConfig, root: Path) -> str:
    """MCP sunucusunun TAM komutu (argümanlarla) ya da adresi; sırlar maskeli."""
    target = server.url or " ".join((server.command, *server.args))
    return _display(target, root)


def _hook_lines(block: Mapping[str, object]) -> list[str]:
    hooks = block.get("hooks")
    lines: list[str] = []
    if not isinstance(hooks, Mapping):
        return lines
    for event, groups in hooks.items():
        for group in groups if isinstance(groups, list) else ():
            if not isinstance(group, Mapping):
                continue
            matcher = str(group.get("matcher") or "").strip()
            head = f"{event} [{matcher}]" if matcher else str(event)
            for hook in group.get("hooks", []) if isinstance(group.get("hooks"), list) else ():
                if isinstance(hook, Mapping):
                    body = hook.get("command") or hook.get("prompt") or hook.get("type") or "?"
                    lines.append(f"{head}: {body}")
    return lines


def _frontmatter(path: Path) -> str:
    try:
        match = _FRONTMATTER.match(path.read_text(encoding="utf-8")[:8_000])
    except (OSError, UnicodeDecodeError):
        return ""
    return match.group(1) if match else ""


def _count_hooks(block: Mapping[str, object]) -> int:
    hooks = block.get("hooks")
    if not isinstance(hooks, Mapping):
        return 0
    return sum(
        len(group.get("hooks", [])) if isinstance(group, Mapping) else 0
        for groups in hooks.values()
        if isinstance(groups, list)
        for group in groups
    )


def _load_json(path: Path, template: str) -> Mapping[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PluginError(template.format(path=path.name, error=error)) from error
    if not isinstance(raw, Mapping):
        raise PluginError(template.format(path=path.name, error="nesne bekleniyordu"))
    return raw


def _substituted(raw: object, root: str) -> object:
    """JSON ağacındaki her metinde eklenti kökü değişkenini çöz."""
    if isinstance(raw, str):
        return substitute_root(raw, root)
    if isinstance(raw, list):
        return [_substituted(item, root) for item in raw]
    if isinstance(raw, Mapping):
        return {key: _substituted(value, root) for key, value in raw.items()}
    return raw


def hook_blocks(layout: PluginLayout) -> tuple[tuple[Path, Mapping[str, object]], ...]:
    """`{"hooks": {...}}` blokları (kök değişkeni çözülmüş); kanca yükleyicisine verilir."""
    root = str(layout.root)
    blocks: list[tuple[Path, Mapping[str, object]]] = []
    for path in layout.hook_files:
        raw = _load_json(path, ERR_HOOKS)
        blocks.append((path, _as_block(_substituted(raw, root), path)))
    if layout.manifest.inline_hooks:
        inline = json.loads(layout.manifest.inline_hooks)
        manifest_path = layout.root / MANIFEST_PATHS[0]
        blocks.append(
            (manifest_path, _as_block(_substituted({"hooks": inline}, root), manifest_path))
        )
    return tuple(blocks)


def _as_block(raw: object, path: Path) -> Mapping[str, object]:
    if not isinstance(raw, Mapping) or not isinstance(raw.get("hooks"), Mapping):
        raise PluginError(ERR_HOOKS.format(path=path.name, error="'hooks' nesnesi yok"))
    return raw


def server_name(plugin: str, server: str) -> str:
    """`plugin_<eklenti>_<sunucu>`: araç adı `plugin_x_y__arac`; kullanıcı kaydıyla çakışmaz."""
    return "plugin_" + _SERVER_SLUG.sub("_", f"{plugin}_{server}").strip("_").lower()


def mcp_servers(layout: PluginLayout) -> tuple[McpServerConfig, ...]:
    """Eklentinin MCP sunucuları; `unreviewed` güvenle (her araç çağrısı onay ister)."""
    return _mcp_servers(layout)[0]


def _mcp_servers(layout: PluginLayout) -> tuple[tuple[McpServerConfig, ...], tuple[str, ...]]:
    """`(sunucular, atlananların uyarıları)`.

    Ölçüldü (31 Ekim): tek bir sunucunun desteklenmeyen alanı (`headers`, `type: sse`, `cwd`…)
    `.mcp.json`'ın tamamını, dolayısıyla eklentinin beceri/komutları dahil HİÇBİR şeyini
    kurulamaz yapıyordu. Sunucular tek tek ayrıştırılır; desteklenmeyen sunucu gerekçeyle
    atlanır. `Authorization: Bearer ${VAR}` başlığı Fusion'ın `token_env` alanına iner.
    """
    root = str(layout.root)
    documents: list[tuple[str, object]] = [
        (path.name, _load_json(path, ERR_MCP)) for path in layout.mcp_files
    ]
    if layout.manifest.inline_mcp:
        documents.append(("plugin.json", {"mcpServers": json.loads(layout.manifest.inline_mcp)}))
    servers: list[McpServerConfig] = []
    skipped: list[str] = []
    for label, raw in documents:
        data = _substituted(raw, root)
        if isinstance(data, Mapping) and "mcpServers" in data:
            data = data["mcpServers"]
        # Claude eklentilerinde kök doğrudan sunucu sözlüğü olabilir.
        if not isinstance(data, Mapping):
            raise PluginError(ERR_MCP.format(path=label, error="'mcpServers' nesne olmalı"))
        for raw_name, entry in data.items():
            try:
                server = _plugin_server(str(raw_name), entry)
            except ConfigError as error:
                skipped.append(WARN_MCP_SKIPPED.format(path=label, server=raw_name, error=error))
                continue
            servers.append(
                replace(server, name=server_name(layout.name, server.name), scope=McpScope.PLUGIN)
            )
    return tuple(servers), tuple(skipped)


_BEARER_REF = re.compile(r"^Bearer\s+\$\{([A-Za-z_][A-Za-z0-9_]*)\}$", re.IGNORECASE)


def _plugin_server(name: str, entry: object) -> McpServerConfig:
    """Tek sunucu; yalnız `Authorization: Bearer ${VAR}` başlığı desteklenir (→ `token_env`)."""
    token_env = ""
    if isinstance(entry, Mapping) and isinstance(entry.get("headers"), Mapping):
        headers = {str(k).lower(): v for k, v in entry["headers"].items()}
        bearer = _BEARER_REF.match(str(headers.pop("authorization", "")).strip())
        if bearer and not headers:
            token_env = bearer.group(1)
            entry = {key: value for key, value in entry.items() if key != "headers"}
    (server,) = parse_project_mcp({"mcpServers": {name: entry}})
    return replace(server, token_env=token_env) if token_env else server


def context_cost(layout: PluginLayout) -> int:
    """Beceri/komut/ajan dizininin her tura eklediği yaklaşık token (Claude "context cost")."""
    chars = 0
    for path in (*layout.skills, *layout.agents, *(p for _n, p in layout.commands)):
        chars += len(layout.name) + 1 + min(len(_frontmatter(path)), 1_024)
    return chars // CHARS_PER_TOKEN


def tree_digest(root: Path) -> str:
    """Klasörün sha256 içerik karması (göreli yol + içerik; bağ hedefi metin olarak)."""
    return _digest(str(root.resolve()), _stat_signature(root))


def _stat_signature(root: Path) -> tuple[tuple[str, int, int], ...]:
    rows: list[tuple[str, int, int]] = []
    total = 0
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
        for name in sorted(files):
            path = Path(current) / name
            info = path.lstat()
            total += info.st_size
            rows.append((path.relative_to(root).as_posix(), info.st_size, info.st_mtime_ns))
            if len(rows) > MAX_PLUGIN_FILES or total > MAX_PLUGIN_BYTES:
                raise PluginError(
                    ERR_TOO_BIG.format(files=MAX_PLUGIN_FILES, mb=MAX_PLUGIN_BYTES // 2**20)
                )
    return tuple(rows)


@functools.lru_cache(maxsize=64)
def _digest(root: str, signature: tuple[tuple[str, int, int], ...]) -> str:
    """İçerik karması; aynı (boyut, mtime) imzası için oturumda bir kez hesaplanır."""
    hasher = hashlib.sha256()
    base = Path(root)
    for relative, _size, _mtime in signature:
        path = base / relative
        hasher.update(relative.encode() + b"\0")
        if path.is_symlink():
            hasher.update(b"->" + str(path.readlink()).encode())
        else:
            hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()
