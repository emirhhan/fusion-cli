"""Plan, kullanıcının AÇIKÇA istediği teslimatları kapsıyor mu?

Ölçüldü (13 Eylül, Dead Cells koşusu): kullanıcı "internetten ücretsiz assetler
toplayarak, hikâye ara sahneleri ve kaliteli bir UI olan, gerçek bir oyun gibi
görünen" bir oyun istedi. Üretilen plan dört adımdı: keşif, proje iskeleti, "oyun
sistemlerini kodla", derleme testi. Assetler, ara sahneler ve UI için TEK BİR ADIM
yoktu; adımların hiçbiri bunları ölçmedi. Koşu "tamamlandı" raporladı ve teslim
edilen şey iki sahne + dört script oldu — yani kullanıcının açıkça istemediğini
söylediği iskelet.

Depoda assetleri doğrulayan mekanizma zaten var (`core.assets`,
`step_verification`); sorun onun HİÇ ÇAĞRILMAMASIYDI, çünkü plan asset adımı
içermiyordu. Bu modül o boşluğu planın kendisinde kapatır: görev bir teslimatı
adıyla istiyorsa, plan da onu adıyla karşılamak zorundadır.

Kapı KELİME düzeyinde çalışır ve bilinçli olarak kabadır: amacı "plan iyi mi"
sorusunu yanıtlamak değil, açıkça istenmiş bir teslimatın planda HİÇ geçmemesini
yakalamaktır. Yanlış tarafa düşmenin bedeli asimetriktir — fazladan bir onarım
denemesi bir model çağrısıdır, atlanan teslimat yanlış "tamamlandı" raporudur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ...core.execution_plan import ExecutionPlan

__all__ = ["DELIVERABLES", "Deliverable", "coverage_instruction", "missing_deliverables"]


@dataclass(frozen=True, slots=True)
class Deliverable:
    """Görevde istenip planda karşılanması gereken bir teslimat."""

    #: Modele ve kullanıcıya söylenecek ad.
    name: str
    #: Görev metninde bu teslimatı İSTEYEN işaretler.
    request_markers: tuple[str, ...]
    #: Planda bu teslimatı KARŞILAYAN işaretler.
    plan_markers: tuple[str, ...]
    #: Plana eklenmesi istenen işin tek cümlelik tarifi.
    instruction: str
    #: Yalnız oyun işlerinde aranır mı? Düşman/dövüş ve hikâye oyun kavramlarıdır;
    #: "test senaryoları yaz" gibi sıradan bir yazılım isteğinde zorunlu sanılmamalı.
    game_only: bool = False


DELIVERABLES: tuple[Deliverable, ...] = (
    Deliverable(
        name="dış varlık (asset) edinimi",
        request_markers=(
            "asset",
            "varlık",
            "sprite",
            "tileset",
            "ses efekt",
            "müzik",
            "yazı tipi",
            "font",
        ),
        plan_markers=("asset", "varlık", "sprite", "tileset", "indir", "download", "font"),
        instruction=(
            "gerçek dosyaları indiren, arşivi açan ve indirilenleri manifestte "
            "(assets/ASSETS.json) kaydeden ayrı bir adım"
        ),
    ),
    Deliverable(
        name="kullanıcı arayüzü (UI)",
        request_markers=("ui", "arayüz", "menü", "hud"),
        plan_markers=("ui", "arayüz", "menü", "hud"),
        instruction="arayüz ekranlarını (menü, HUD) üreten ayrı bir adım",
    ),
    Deliverable(
        name="düşman ve dövüş",
        # "Dead Cells benzeri" demek dövüş demektir: oyunun çekirdek döngüsü
        # düşmanla karşılaşmaktır. Ölçüldü (13 Eylül, koşu 32): oyun çalıştı,
        # assetler ve hareket tamamdı; kullanıcı ilk cümlede "düşman yok,
        # saldıracağımız bir şey yok" dedi. Plan hiçbir adımda düşman anmamıştı.
        request_markers=(
            "deadcells",
            "dead cells",
            "dövüş",
            "savaş",
            "düşman",
            "enemy",
            "enemies",
            "combat",
            "boss",
            "roguelike",
            "hack and slash",
        ),
        plan_markers=("düşman", "enemy", "enemies", "dövüş", "savaş", "combat", "boss", "hasar"),
        instruction=(
            "düşmanları üreten ve oyuncuyla dövüşünü (hasar alma/verme) kuran ayrı bir adım"
        ),
        game_only=True,
    ),
    Deliverable(
        name="hikâye / ara sahne",
        # Yalın "senaryo" İSTEK işareti DEĞİL: "test senaryoları yaz" hikâye
        # istemez (A3-02). Plan tarafında hâlâ kapsayıcı sayılır.
        request_markers=("ara sahne", "arasahne", "cutscene", "hikaye", "hikâye"),
        plan_markers=("ara sahne", "arasahne", "cutscene", "hikaye", "hikâye", "senaryo"),
        instruction="hikâye metnini ve ara sahne akışını üreten ayrı bir adım",
        game_only=True,
    ),
)


#: Görevin bir OYUN işi olduğunu gösteren işaretler (`game_only` teslimatların kapısı).
_GAME_MARKERS = (
    "oyun",
    "game",
    "godot",
    "unity",
    "roguelike",
    "dead cells",
    "deadcells",
    "platformer",
)


def _contains(marker: str, text: str) -> bool:
    """İşaret METNİN BİR SÖZCÜĞÜNÜN BAŞINDA mı geçiyor?

    Eskiden alt dize eşleşmesiydi: `"ui"` "build", "required", "quiz" içinde de
    bulunuyor, bu yüzden istek tarafında olmayan UI zorunlu sanılıyor, plan
    tarafında ise "build" gerçek UI eksiğini gizliyordu (A3-02, ölçüldü 29 Ekim).
    Türkçe ekler korunur (`assetler`, `arayüzü`): yalnız SÖZCÜK BAŞI aranır; en çok üç
    harfli kısa işaretler (`ui`, `hud`) ek olarak sözcük SONU da ister (`UI'ı` geçer).
    """
    kalip = rf"(?<!\w){re.escape(marker)}" + (r"(?!\w)" if len(marker) <= 3 else "")
    return re.search(kalip, text) is not None


def _plan_metni(plan: ExecutionPlan) -> str:
    """Planın kapsama açısından okunacak tüm metni.

    Adım kimliği, hedef, başarı koşulu ve beklenen etkiler birlikte okunur: plan
    teslimatı bunlardan HERHANGİ birinde adıyla anıyorsa kapsanmış sayılır.
    """
    parcalar: list[str] = []
    for step in plan.steps:
        parcalar.append(step.step_id)
        parcalar.append(step.goal)
        parcalar.append(step.verification_hint)
        parcalar.extend(step.success_criteria)
        parcalar.extend(step.expected_effects)
    return " ".join(parcalar).casefold()


def missing_deliverables(task: str, plan: ExecutionPlan) -> tuple[Deliverable, ...]:
    """Görevde istenip planda hiç geçmeyen teslimatlar."""
    istek = task.casefold()
    kapsam = _plan_metni(plan)
    oyun_isi = any(_contains(isaret, istek) for isaret in _GAME_MARKERS)
    return tuple(
        teslimat
        for teslimat in DELIVERABLES
        if (oyun_isi or not teslimat.game_only)
        and any(_contains(isaret, istek) for isaret in teslimat.request_markers)
        and not any(_contains(isaret, kapsam) for isaret in teslimat.plan_markers)
    )


def coverage_instruction(eksikler: tuple[Deliverable, ...]) -> str:
    """Onarım isteminin başına konan, NE EKSİK olduğunu söyleyen metin.

    Eksiği yalnız adlandırmak yetmez; model aynı planı "zaten kapsıyor" diye
    yeniden üretebilir. Bu yüzden her eksik için EKLENECEK ADIM tarif edilir.
    """
    satirlar = [f"- {teslimat.name}: {teslimat.instruction}" for teslimat in eksikler]
    return (
        "ÖNCEKİ PLANIN EKSİK: kullanıcının açıkça istediği şu teslimatlar için adım yok.\n"
        + "\n".join(satirlar)
        + "\nBunları ayrı adımlar olarak ekle; var olan adımların içine gömme. "
        "Her yeni adımın başarı koşulu DOSYAYLA ölçülebilir olmalı."
    )
