"""Depo haritasının sistem bağlamına girmesi.

`core/repo_map.py` haritayı üretir; bu modül onu hangi bütçeyle ve hangi başlıkla
vereceğimizi tanımlar. Ayrım bilinçlidir: harita üretimi saf ve test edilebilir
kalsın, politika motor katmanında dursun. Haritanın hangi turda ekleneceğine
(`run_agent`: kod kipinde, kök turda) görev türü karar vermez.

Denetlendi (6 Eylül): harita modülü yazılmış ama hiçbir yerden çağrılmıyordu — model
onu hiç görmüyordu. Modülün var olması, Fusion'ın onu kullanabildiği anlamına gelmez.
"""

from __future__ import annotations

from dataclasses import dataclass
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


def repo_map_with_stats(root: Path, *, budget_chars: int = MAP_BUDGET_CHARS) -> RepoMapBlock:
    """Kökte kod varsa başlıklı harita bloğu ve ölçümü; yoksa boş blok."""
    sonuc = build_repo_map_report(root, budget_chars=budget_chars)
    if not sonuc.text:
        return RepoMapBlock("", None)
    blok = (
        "# Depo haritası (en çok başvurulan tanımlar)\n"
        "Dosyayı aramadan önce buraya bak; liste kısaltılmıştır, tam değildir.\n"
        f"{sonuc.text}"
    )
    return RepoMapBlock(blok, sonuc.stats)


def repo_map_block(root: Path, budget_chars: int = MAP_BUDGET_CHARS) -> str:
    """Kökte kod varsa başlıklı harita bloğu üret; yoksa boş metin.

    Görev türüne bakılmaz: tür kelime sayımıyla tahmin ediliyordu ve kısa bir
    devam mesajında haritayı düşürüyordu. Harita bütçeyle sınırlıdır; dosyalar
    değişmedikçe metni turdan tura aynıdır ve web sohbetinin öneki kaymaz.
    """
    return repo_map_with_stats(root, budget_chars=budget_chars).text
