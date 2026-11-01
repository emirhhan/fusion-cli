"""Depo haritasının sistem bağlamına girmesi.

`core/repo_map.py` haritayı üretir; bu modül onu hangi bütçeyle ve hangi başlıkla
vereceğimizi tanımlar. Ayrım bilinçlidir: harita üretimi saf ve test edilebilir
kalsın, politika motor katmanında dursun. Haritanın hangi turda ekleneceğine
(`run_agent`: kod kipinde, kök turda) görev türü karar vermez.

Denetlendi (6 Eylül): harita modülü yazılmış ama hiçbir yerden çağrılmıyordu — model
onu hiç görmüyordu. Modülün var olması, Fusion'ın onu kullanabildiği anlamına gelmez.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import islice
from pathlib import Path

from ...config.models import Config
from ...core.repo_map import DEFAULT_BUDGET_CHARS, RepoMapStats, build_repo_map_report
from .context_budget import CHARS_PER_TOKEN_ESTIMATE, context_budget

#: Haritaya ayrılan varsayılan bağlam bütçesi (`runtime.repo_map_chars` ile değişir).
#
# Aider'ın repo-map varsayılanı ~1k token; burada 3 karakter/token ile 3.000 karakter.
# Harita YÖNLENDİRİR, dosyanın yerini söyler; kodu taşımaz. Ölçüldü (30 Ekim, fusion-cli):
# 1.500 karakter yalnız 10 dosyaya, 3.000 karakter 18 dosyaya yetiyor; bu deponun en çok
# içe aktarılan 20 dosyasından 10 / 16'sı görünüyor (eski sayımda 0 / 2).
MAP_BUDGET_CHARS = DEFAULT_BUDGET_CHARS

#: Harita bir modelin giriş penceresinin en çok bu kadarını tutar. Küçük pencereli (zayıf)
#: modelde context rot erken başlar ve harita her kök turda sistem bağlamındadır; 3.000
#: karakter 32k pencerenin ~%3'üdür, bu oranın altına inen pencerelerde harita küçülür.
#: TAHMİN: canlı ölçümle güncellenecek. Pencere bilinmiyorsa ayardaki değer aynen kullanılır.
MAP_WINDOW_SHARE = 0.03
#: Küçülen haritanın tabanı: bundan azı birkaç satırdır, bilgi taşımaz.
MAP_MIN_CHARS = 600

#: Güvenilmeyen görev metninden odak çıkarma sınırları; dosya içeriği okunmaz.
TASK_FOCUS_MAX_CHARS = 8192
TASK_FOCUS_MAX_TOKENS = 128
TASK_FOCUS_MAX_ITEMS = 16
TASK_FOCUS_MAX_TOKEN_CHARS = 256
_FOCUS_TOKEN = re.compile(r"[^\s`'\"<>(){}\[\],;]+")
_FOCUS_LINE = re.compile(r":\d+(?::\d+)?$")


@dataclass(frozen=True, slots=True)
class RepoMapFocus:
    """Görevden çıkarılmış sınırlı, köke göreli yollar ve sembol adları."""

    paths: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()


def task_focus(root: Path, task: str) -> RepoMapFocus:
    """Görevdeki açık yol ve adları çıkar; kök dışını ve aşırı girdiyi ele."""
    paths: list[str] = []
    symbols: dict[str, bool] = {}
    resolved_root = root.resolve()
    text = task[:TASK_FOCUS_MAX_CHARS]
    tokens = _FOCUS_TOKEN.finditer(text)
    previous_end = 0
    is_in_code = False
    for match in islice(tokens, TASK_FOCUS_MAX_TOKENS):
        if text[previous_end : match.start()].count("`") % 2:
            is_in_code = not is_in_code
        previous_end = match.end()
        token = _FOCUS_LINE.sub("", match.group().rstrip(":.!?"))
        if not token or len(token) > TASK_FOCUS_MAX_TOKEN_CHARS:
            continue
        if "/" in token or "\\" in token or "." in token:
            relative = _focus_path(resolved_root, token)
            if relative and relative not in paths and len(paths) < TASK_FOCUS_MAX_ITEMS:
                paths.append(relative)
        elif token.isidentifier():
            is_explicit = (
                is_in_code
                or "_" in token
                or any(character.isupper() for character in token[1:])
                or text[match.end() : match.end() + 1] == "("
            )
            _remember_focus_symbol(symbols, token, is_explicit=is_explicit)
    ordered_symbols = sorted(symbols, key=lambda symbol: not symbols[symbol])
    return RepoMapFocus(tuple(paths), tuple(ordered_symbols))


def _remember_focus_symbol(symbols: dict[str, bool], token: str, *, is_explicit: bool) -> None:
    """Açık kod adı düzyazıyı kotadan çıkarabilir; toplam aday sayısı büyümez."""
    if token in symbols:
        symbols[token] = symbols[token] or is_explicit
        return
    if len(symbols) >= TASK_FOCUS_MAX_ITEMS:
        if not is_explicit:
            return
        prose = next((symbol for symbol in reversed(symbols) if not symbols[symbol]), None)
        if prose is None:
            return
        del symbols[prose]
    symbols[token] = is_explicit


def _focus_path(root: Path, token: str) -> str | None:
    """Yalnız proje kökü içinde kalan normalize odağı döndür; kaynak okuma yok."""
    if "\\" in token or "\x00" in token:
        return None
    try:
        relative = (root / token).resolve().relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    return relative.as_posix() if relative.parts else None


@dataclass(frozen=True, slots=True)
class RepoMapBlock:
    """Sistem bağlamına girecek harita bloğu ve ölçümü (kod yoksa ikisi de boş)."""

    text: str
    stats: RepoMapStats | None


def effective_budget(configured: int, window_tokens: int | None) -> int:
    """Ayardaki bütçeyi modelin penceresine göre sınırla (0 = harita kapalı)."""
    if configured <= 0:
        return 0
    if not window_tokens:
        return configured
    cap = int(window_tokens * CHARS_PER_TOKEN_ESTIMATE * MAP_WINDOW_SHARE)
    return min(configured, max(MAP_MIN_CHARS, cap))


def map_budget_for(config: Config) -> int:
    """Turun etkin harita bütçesi: `runtime.repo_map_chars` ve modelin penceresi."""
    runtime = getattr(config, "runtime", None)
    configured = getattr(runtime, "repo_map_chars", MAP_BUDGET_CHARS)
    window: int | None = None
    try:
        window = context_budget(config, config.agent).window_tokens
    except (AttributeError, TypeError, ValueError):
        # Pencere ölçülemedi (eksik yapılandırma): ayardaki bütçe aynen geçerli.
        window = None
    return effective_budget(configured, window)


def repo_map_with_stats(
    root: Path,
    *,
    budget_chars: int = MAP_BUDGET_CHARS,
    focus_paths: tuple[str, ...] = (),
    focus_symbols: tuple[str, ...] = (),
) -> RepoMapBlock:
    """Kökte kod varsa başlıklı harita bloğu ve ölçümü; yoksa boş blok."""
    sonuc = build_repo_map_report(
        root, budget_chars=budget_chars, focus_paths=focus_paths, focus_symbols=focus_symbols
    )
    if not sonuc.text:
        return RepoMapBlock("", None)
    blok = (
        "# Depo haritası (en çok başvurulan tanımlar)\n"
        "Dosyayı aramadan önce buraya bak; liste kısaltılmıştır, tam değildir.\n"
        f"{sonuc.text}"
    )
    return RepoMapBlock(blok, sonuc.stats)


def repo_map_block(
    root: Path,
    budget_chars: int = MAP_BUDGET_CHARS,
    *,
    focus_paths: tuple[str, ...] = (),
    focus_symbols: tuple[str, ...] = (),
) -> str:
    """Kökte kod varsa başlıklı harita bloğu üret; yoksa boş metin.

    Görev türüne bakılmaz: tür kelime sayımıyla tahmin ediliyordu ve kısa bir
    devam mesajında haritayı düşürüyordu. Harita bütçeyle sınırlıdır; dosyalar
    değişmedikçe metni turdan tura aynıdır ve web sohbetinin öneki kaymaz.
    """
    return repo_map_with_stats(
        root, budget_chars=budget_chars, focus_paths=focus_paths, focus_symbols=focus_symbols
    ).text
