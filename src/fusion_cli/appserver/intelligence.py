"""Zeka ayarları: yapılandırmada ve kodda var olan zekâ özelliklerini uygulamadan yönet.

Bu özellikler daha önce yalnız `config.yaml` ya da terminal komutlarıyla açılıp kapanıyordu;
uygulama kullanıcısı onları göremiyordu. Burada her bayrak insan diliyle anlatılır, maliyeti
söylenir ve değişiklik hem kalıcı yapılandırmaya yazılır hem çalışan oturuma uygulanır.

Varsayılanlar DEĞİŞTİRİLMEZ: kapalı gelenler (ör. görsel doğrulama) ölçümle bilinçli kapalıdır
(bkz. `config/defaults.yaml`); kullanıcı burada açıkça açar.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from ..cli.repl.state import Engine, ReplState
from ..config.models import Config
from ..config.writer import (
    WORKFLOW_MODE_VALUES,
    write_runtime_flag,
    write_workflow_mode,
)
from ..core.execution_mode import ExecutionMode
from .runtime_prefs import persist_engine


@dataclass(frozen=True, slots=True)
class FlagSpec:
    """Arayüzde görünen tek bir zekâ anahtarı."""

    key: str
    label: str
    description: str
    cost: str
    group: str
    #: `True` ise arayüzdeki "açık" yapılandırmadaki değerin TERSİDİR (ör. `teacherless`).
    inverted: bool = False


FLAGS: tuple[FlagSpec, ...] = (
    FlagSpec(
        "self_review",
        "Öz-denetim",
        "Görev bitince denetçi model sonucu kontrol eder, somut "
        "sorun bulursa bir düzeltme turu yapar.",
        "Her görevde bir ek model çağrısı",
        "Kalite",
    ),
    FlagSpec(
        "reflexion",
        "Hatadan ders alma (yansıma)",
        "Araç hata verince model 'ne yanlış gitti, farklı yaklaş' "
        "notu alır; körlemesine tekrar azalır.",
        "Ek model çağrısı yok",
        "Kalite",
    ),
    FlagSpec(
        "lessons",
        "Kendini geliştirme (dersler)",
        "Her görevden ders çıkarılır, benzer görevlerde "
        "hatırlatılır. Fusion zamanla senin işine uyum sağlar.",
        "Görev başına bir ek model çağrısı",
        "Öğrenme",
    ),
    FlagSpec(
        "teacherless",
        "Öğretmene danış",
        "Zorlandığında güçlü bir 'öğretmen' modele danışabilir ve dersini hatırlar.",
        "Danışılan her seferde ek çağrı",
        "Öğrenme",
        inverted=True,
    ),
    FlagSpec(
        "teacher_lesson_sync",
        "Öğretmen derslerini belleğe yaz",
        "Öğretmenin cevabından çıkan ders, model sonradan geri "
        "çağırabilsin diye ders belleğine de yazılır.",
        "Ek maliyet yok",
        "Öğrenme",
    ),
    FlagSpec(
        "web_verification",
        "Web çıktısını mekanik denetle",
        "Ürettiği HTML/CSS/JS'te kırık görsel, boş bağlantı, "
        "eksik bölüm gibi sorunları bulup düzeltir.",
        "Ek model çağrısı yok",
        "Doğrulama",
    ),
    FlagSpec(
        "browser_verification",
        "Sayfayı gerçekten açıp ölç",
        "Üretilen sayfayı tarayıcıda açar; konsol hatası, "
        "yüklenmeyen kaynak ve yatay taşmayı ölçer.",
        "Playwright gerekir; yoksa sessizce atlanır",
        "Doğrulama",
    ),
    FlagSpec(
        "visual_verification",
        "Görsel doğrulama (görme modeliyle)",
        "Sayfayı bölgelere ayırıp görme modeline dar sorular sorar "
        "(başlık tek satır mı, metin okunuyor mu).",
        "Soru başına ayrı model çağrısı; ücretsiz modellerde güvenilmez olabilir",
        "Doğrulama",
    ),
    FlagSpec(
        "playbooks",
        "Hazır akışlar (playbook)",
        "İstek hazır bir çok adımlı akışa uyarsa serbest döngü "
        "yerine o deterministik akış çalışır.",
        "Genelde daha az model çağrısı",
        "Yürütme",
    ),
    FlagSpec(
        "synthesis",
        "Fusion: cevapları birleştir",
        "Fusion motorunda hakem en iyiyi seçtikten sonra tüm "
        "cevapların iyi yanlarını tek cevapta birleştirir.",
        "Ek model çağrısı; yalnız Fusion motorunda",
        "Fusion motoru",
    ),
    FlagSpec(
        "verified_synthesis",
        "Fusion: hakem kararıyla sentez",
        "Sentez hakemin kararını görerek çalışır; zayıf adayın hatası cevaba sızmaz.",
        "Daha yavaş (hakem ve sentez seri); yalnız Fusion motorunda",
        "Fusion motoru",
    ),
)

_FLAGS_BY_KEY = {flag.key: flag for flag in FLAGS}

ENGINE_LABELS = {
    Engine.AGENT.value: "Tek ajan — araçlarla çalışan, hızlı ve ekonomik motor",
    Engine.FUSION.value: "Fusion — aynı soruyu birden çok modele sorar, hakem seçer, sentezler",
}
WORKFLOW_LABELS = {
    "off": "Tek döngü — model gerektiğinde kendi planını tutar",
    "always": "Plan motoru — her görev önce plan, adım adım yürütme ve kanıtlı doğrulama",
}


def _flag_enabled(config: Config, flag: FlagSpec) -> bool:
    value = bool(getattr(config.runtime, flag.key))
    return not value if flag.inverted else value


def status(state: ReplState) -> dict[str, Any]:
    """`zeka.durum`: motor, plan kipi ve her anahtarın güncel değeri."""
    config = state.config
    return {
        "ok": True,
        "motor": state.engine.value,
        "motorlar": [{"deger": value, "etiket": label} for value, label in ENGINE_LABELS.items()],
        "planKipi": config.runtime.workflow_mode.value,
        "planKipleri": [
            {"deger": value, "etiket": WORKFLOW_LABELS[value]} for value in WORKFLOW_MODE_VALUES
        ],
        "ogretmenTanimli": config.teacher is not None,
        "bayraklar": [
            {
                "anahtar": flag.key,
                "etiket": flag.label,
                "aciklama": flag.description,
                "maliyet": flag.cost,
                "grup": flag.group,
                "acik": _flag_enabled(config, flag),
            }
            for flag in FLAGS
        ],
    }


def apply(state: ReplState, data: object) -> dict[str, Any]:
    """`zeka.ayarla`: `{anahtar, deger}`; kalıcı yaz, sonra çalışan oturuma uygula."""
    if not isinstance(data, dict):
        return {"ok": False, "metin": "Geçersiz istek."}
    key, value = data.get("anahtar"), data.get("deger")
    if key == "motor":
        return _apply_engine(state, value)
    if key == "planKipi":
        return _apply_workflow(state, value)
    flag = _FLAGS_BY_KEY.get(key) if isinstance(key, str) else None
    if flag is None:
        return {"ok": False, "metin": f"Bilinmeyen zeka ayarı: {key}"}
    if not isinstance(value, bool):
        return {"ok": False, "metin": "Değer açık/kapalı olmalı."}
    stored = not value if flag.inverted else value
    try:
        write_runtime_flag(state.config, flag.key, stored)
    except (OSError, ValueError) as error:
        return {"ok": False, "metin": f"Ayar kaydedilemedi: {error}"}
    changes: dict[str, Any] = {flag.key: stored}  # anahtar yukarıdaki beyaz listeden gelir
    runtime = replace(state.config.runtime, **changes)
    state.config = replace(state.config, runtime=runtime)
    return status(state)


def _apply_engine(state: ReplState, value: object) -> dict[str, Any]:
    try:
        state.engine = Engine(str(value))
    except ValueError:
        valid = ", ".join(ENGINE_LABELS)
        return {"ok": False, "metin": f"Geçersiz motor: {value}. Seçenekler: {valid}"}
    error = persist_engine(state.config, state.engine.value)
    if error is not None:
        return {"ok": False, "metin": error}
    return status(state)


def _apply_workflow(state: ReplState, value: object) -> dict[str, Any]:
    if value not in WORKFLOW_MODE_VALUES:
        return {"ok": False, "metin": f"Geçersiz plan kipi: {value}"}
    try:
        write_workflow_mode(state.config, str(value))
    except (OSError, ValueError) as error:
        return {"ok": False, "metin": f"Ayar kaydedilemedi: {error}"}
    runtime = replace(state.config.runtime, workflow_mode=ExecutionMode(str(value)))
    state.config = replace(state.config, runtime=runtime)
    return status(state)
