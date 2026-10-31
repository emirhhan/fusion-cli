"""Zayıf modele görev türüne göre SABİT araç alt kümesi (yol haritası 4. adım).

Ölçüldü (30 Ekim): sıkı yüzeydeki zayıf model, masaüstü/Chrome ailesi gizlendikten sonra
bile 36 şema ve ~16,6 bin karakter alıyordu (tarayıcı 10, site 4, medya, sürü araçları,
önizleme...). "Kod düzenle" isteyen modele `browser_*` ve `clone_site` göstermek araç
seçimini bozar (IBM LongFuncEval: araç sayısı artınca %7-85 düşüş) ve bağlamı yer.

Tasarım:

- Profil, ARAÇ GİZLEMEDİR (dışlama): her profil bir küme yerleşik aracı gizler; listede
  olmayan yeni araç görünür kalır. MCP/eklenti araçlarına dokunulmaz (`compact_external_tools`
  onları zaten sınırlar). Açıkça istenen (`allowed_tools`) araç gizlenmez.
- Tür, MEVCUT sınıflayıcılardan gelir (`is_game_task`, `is_desktop_task`, etki sınıfı
  `required_effect_for`, görev türü `classify_task`); model çağrısı yok.
- Profil KONUŞMA düzeyindedir ve yalnız GENİŞLER: konuşmadaki bütün gerçek kullanıcı
  isteklerinin profillerinin birleşimidir. Salt "ilk istek" seçilseydi okuma sorusuyla
  başlayan sohbette sonraki "şunu düzelt" isteği düzenleme aracı bulamazdı (rota kararında
  aynı miras hatası ölçülmüştü, bkz. `execution_route`). Birleşim, geçmişin türevi olduğu
  için durumsuzdur: tur başına yeniden kurulan `AgentDeps` ile de aynı sonucu verir ve
  yüzey (dolayısıyla önek) yalnız kullanıcı gerçekten yeni tür istediğinde değişir.
- Belirsiz istek (selam, "tamam") profil üretmez ve mevcut profili daraltmaz; hiç profil
  yoksa bugünkü sıkı yüzey aynen kalır.
- Profil dışı bir araç ADIYLA çağrılırsa çağrı çalışır ve yüzey o tur için bir kez
  `WIDENED_KIND` işaretiyle genişler (bkz. `loop._execute`). Sert ret seçilmedi: yanlış
  sınıflanmış bir istekte kullanıcının işi sessizce yapılamaz hale gelirdi; yönlendirme
  mesajı ise modele yeni bir tur harcatırdı. Genişleme ölçülebilir olay bırakır.
"""

from __future__ import annotations

from collections.abc import Sequence

from ...core.types import Message
from ..effects.detect import required_effect_for
from ..effects.model import EffectKind
from .classify import TaskKind, classify_task
from .expertise import is_desktop_task, is_game_task, is_remotion_task
from .history import is_summary_message

PROFILE_QUESTION = "soru"
PROFILE_CODE = "kod"
PROFILE_WEB = "web"
PROFILE_MEDIA = "medya"
PROFILE_DESKTOP = "masaustu"

#: Profil dışı çağrıyla yüzeyin bu tur için genişletildiğini belirten `task_kinds` işareti.
WIDENED_KIND = "profil_genisledi"

#: Her isteğin sınıflandırılacağı en fazla karakter (geçmişte çok uzun yapıştırmalar olur).
_CLASSIFY_CHARS = 6_000

_WRITE = frozenset(
    {"edit_file", "multi_edit", "write_file", "make_tool", "scaffold_web", "extract_archive"}
)
_PREVIEW = frozenset(
    {"start_preview", "preview_console", "preview_network", "preview_screenshot"}
)
_BROWSER = frozenset(
    {
        "browser_open", "browser_click", "browser_type", "browser_read", "browser_screenshot",
        "browser_mirror", "browser_tab_open", "browser_tab_select", "browser_tabs_list",
        "browser_close",
    }
)  # fmt: skip
_SITE = frozenset({"site_crawl", "site_design", "clone_site", "download_file"})
_MEDIA = frozenset(
    {
        "scaffold_remotion", "revise_remotion_scenes", "render_remotion", "optimize_image",
        "generate_image", "play_probe",
    }
)  # fmt: skip
_SWARM = frozenset({"spawn_agents", "council"})

#: Profil → o profilde GİZLENEN yerleşik araçlar.
PROFILE_HIDDEN: dict[str, frozenset[str]] = {
    PROFILE_QUESTION: _WRITE | _PREVIEW | _BROWSER | _SITE | _MEDIA | _SWARM,
    PROFILE_CODE: _BROWSER | _SITE | _MEDIA | _SWARM,
    PROFILE_WEB: _MEDIA | _SWARM,
    PROFILE_MEDIA: _SITE | _SWARM,
    PROFILE_DESKTOP: _MEDIA | _SWARM,
}

_READ_EFFECTS = frozenset({EffectKind.WORKSPACE_READ.value, "bulk_count"})
_WEB_EFFECTS = frozenset({EffectKind.WEB_LOOKUP.value})
_CODE_KINDS = frozenset(
    {TaskKind.BUGFIX, TaskKind.REFACTOR, TaskKind.TEST, TaskKind.FEATURE, TaskKind.DOCS}
)


def classify_tool_profiles(task: str) -> frozenset[str]:
    """Tek bir isteğin gerektirdiği profiller; belirsizse boş küme."""
    text = task[:_CLASSIFY_CHARS]
    profiles: set[str] = set()
    if is_game_task(text) or is_remotion_task(text):
        profiles.add(PROFILE_MEDIA)
    if is_desktop_task(text):
        profiles.add(PROFILE_DESKTOP)
    effect = required_effect_for(text)
    if effect in _READ_EFFECTS:
        profiles.add(PROFILE_QUESTION)
    elif effect in _WEB_EFFECTS:
        profiles.add(PROFILE_WEB)
    elif effect is not None:
        profiles.add(PROFILE_CODE)
    else:
        kind = classify_task(text)
        if kind in _CODE_KINDS:
            profiles.add(PROFILE_CODE)
        elif kind is TaskKind.WEBSITE:
            profiles.add(PROFILE_WEB)
        elif kind is TaskKind.EXPLORE:
            profiles.add(PROFILE_QUESTION)
    return frozenset(profiles)


def _is_user_request(message: Message) -> bool:
    return message.role == "user" and not message.harness_note and not is_summary_message(message)


def conversation_tool_profiles(task: str, history: Sequence[Message] = ()) -> tuple[str, ...]:
    """Konuşmanın profili: geçmişteki gerçek kullanıcı istekleri + bu istek, birleşim."""
    found: set[str] = set()
    for message in history:
        if _is_user_request(message):
            found |= classify_tool_profiles(message.content)
    found |= classify_tool_profiles(task)
    return tuple(sorted(found))


def hidden_tools(profiles: Sequence[str]) -> frozenset[str]:
    """Birleşik profilde gizli kalan araçlar: profillerin gizlemelerinin KESİŞİMİ."""
    known = [PROFILE_HIDDEN[name] for name in profiles if name in PROFILE_HIDDEN]
    if not known:
        return frozenset()
    return frozenset.intersection(*known)
