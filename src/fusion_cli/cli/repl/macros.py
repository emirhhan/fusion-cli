"""Agent makroları — sık yapılan işleri tek komuta indiren hazır görevler.

Bir makro iki şey yapar: agent motoruna hazır bir görev metni verir ve gerekiyorsa
sistem promptuna bir davranış kipi ekler. Makro çalıştırmak, o metni elle yazmakla
aynı şeydir; sihir yoktur.

Kipler ayrı tutulur çünkü davranışı değiştirirler:

- **goal** — hedefe ulaşana kadar pes etmez, adım sınırı yükselir.
- **grill-me** — kod yazmadan önce gereksinimleri sorularla netleştirir.
- **plan-yurut** — görevi tek döngü yerine plan motorunda (adım kanıtı,
  checkpoint/devam, final kabulü) yürütür. Varsayılan yol tek döngüdür; plan
  motoru yalnız bu seçimle ya da `workflow_mode: always` ile çalışır.

Diğer makrolar (bug, commit, review, browser, simplify, security-review, debug, batch)
yalnızca hazır görev metnidir; agent'ın davranışını değiştirmezler. Claude Code'un
yerleşik iş-akışı becerileriyle (`/simplify`, `/security-review`, `/debug`, `/batch`)
aynı adı taşırlar; kullanıcı `.claude/skills/<ad>/SKILL.md` ile gövdeyi önceleyebilir
(bkz. `commands._macro`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

#: Uzun şablonlar koda gömülmez; paket verisi olarak okunur (RULES "Dil").
_PROMPTS = Path(__file__).resolve().parents[2] / "engines" / "agent" / "prompts"
SECURITY_REVIEW_PROMPT = (_PROMPTS / "security_review.md").read_text(encoding="utf-8")
#: `/security-review` argümansız çağrıldığında denetlenen kapsam.
SECURITY_REVIEW_DEFAULT_SCOPE = "çalışma ağacındaki tüm değişiklikler (staged ve unstaged)"


class Mode(Enum):
    """Makronun sistem promptuna eklediği davranış kipi."""

    NONE = "none"
    GOAL = "goal"
    GRILL = "grill"
    WORKFLOW = "workflow"


@dataclass(frozen=True, slots=True)
class Macro:
    """Hazır bir agent görevi."""

    #: Kullanıcı argümanı yoksa kullanılacak görev metni.
    task: str
    mode: Mode = Mode.NONE
    #: Argüman verildiğinde metne nasıl yerleştirileceği. Boşsa argüman metnin
    #: yerini alır.
    template: str = ""
    #: Kullanıcı argüman vermezse çalıştırılabilir mi?
    argument_required: bool = False

    def build(self, argument: str) -> str:
        """Kullanıcı argümanından çalıştırılacak görev metnini üret."""
        text = argument.strip()
        if not text:
            return self.task
        return self.template.format(argument=text) if self.template else text


GOAL_PROMPT = """<hedef_kipi>
HEDEF KİPİNDESİN. Verilen görevi tamamlayana kadar pes etmek yok.

- Bir araç ya da komut hata verirse farklı bir yol dene: başka bayraklar, başka
  araç, başka yaklaşım. Aynı çağrıyı tekrarlama.
- Kendi başına aşamayacağın bir engel ya da eksik bilgi varsa `ask_user` ile
  kullanıcıdan müdahale iste; sessizce vazgeçme.
- Görev gerçekten bitmeden nihai cevap verme.
</hedef_kipi>"""

GRILL_PROMPT = """<mülakat_kipi>
GEREKSİNİM ANALİZİ KİPİNDESİN. Hemen kod ya da çözüm üretme.

Önce `ask_user` ile kullanıcıyı sorularla netleştir: ne istediğini tam olarak
anlayana, mimari tercihler (veritabanı, çerçeve, biçim) ve sınırlar belirginleşene
kadar sor. Sorular kısa ve tek konulu olsun.

İkna olduğunda asıl işe başla ve neyi neden yaptığını tek cümleyle söyle.
</mülakat_kipi>"""

MODE_PROMPTS = {Mode.GOAL: GOAL_PROMPT, Mode.GRILL: GRILL_PROMPT}

#: Kipin agent turuna verdiği adım sınırı. Hedef kipi pes etmemeli; terminal ve
#: masaüstü aynı değeri buradan okur ki iki yüzey ayrışmasın.
MODE_STEP_LIMITS = {Mode.GOAL: 100}

MACROS: dict[str, Macro] = {
    "goal": Macro(
        task="Proje hedefini belirle ve tamamla.",
        mode=Mode.GOAL,
    ),
    "grill-me": Macro(
        task="",
        mode=Mode.GRILL,
        template="Kullanıcı şunu istiyor: '{argument}'",
        argument_required=True,
    ),
    "bug": Macro(
        task="Projeyi ve kodları inceleyerek bir hata bul ve düzelt. Önce hatayı "
        "yeniden üret ya da testle göster, sonra kök nedeni bul, en dar düzeltmeyi "
        "uygula ve testlerle doğrula.",
        template="Şu hatayı bul ve düzelt: {argument}. Önce kök nedeni tespit et, "
        "sonra en dar düzeltmeyi uygula ve doğrula.",
    ),
    "commit": Macro(
        task="`git status` ve `git diff` ile değişiklikleri incele, mantıklı bir "
        "conventional commit mesajı üret ve commit'le. İlgisiz dosyaları ekleme.",
        template="Değişiklikleri incele ve şu bağlamla commit'le: {argument}",
    ),
    "review": Macro(
        task="`git diff` ile mevcut değişiklikleri (staged ve unstaged) oku ve "
        "güvenlik, doğruluk ve mimari açısından ayrıntılı bir code review yap. "
        "Bulguları önem sırasına göre, dosya:satır referanslarıyla ver.",
        template="Şunu code review yap: {argument}. Güvenlik, doğruluk ve mimari "
        "açısından incele, dosya:satır referansı ver.",
    ),
    "plan-yurut": Macro(
        task="",
        mode=Mode.WORKFLOW,
        argument_required=True,
    ),
    "browser": Macro(
        task="",
        template="Web'de araştır: {argument}. `web_search` ile ara, `web_fetch` ile "
        "kaynakları oku, bulguları kaynak bağlantılarıyla özetle.",
        argument_required=True,
    ),
    "btw": Macro(
        task="",
        template=(
            "Ana görevi değiştirmeden şu yan soruyu kısa ve doğrudan yanıtla: {argument}. "
            "Yanıtı ana görevin çalışma planına veya dosya değişikliklerine uygulama; "
            "kullanıcı ayrıca isterse ana göreve dön."
        ),
        argument_required=True,
    ),
    "simplify": Macro(
        task="Çalışma ağacındaki değişen kodu (`git diff`, staged ve unstaged) yeniden "
        "kullanım, sadeleştirme, verimlilik ve soyutlama düzeyi açısından incele: tekrar "
        "eden mantığı mevcut yardımcıya bağla, gereksiz dalları ve ölü kodu kaldır, "
        "pahalı işlemleri sadeleştir. Hata avı YAPMA (onun için /review). Davranışı "
        "değiştirmeden düzeltmeleri uygula ve ilgili testleri koşturup sonucu bildir.",
        template="Şunu sadeleştir: {argument}. Yeniden kullanım, sadeleştirme, verimlilik "
        "ve soyutlama düzeyi açısından incele; davranışı değiştirmeden düzeltmeleri uygula "
        "ve ilgili testleri koşturup sonucu bildir. Hata avı yapma.",
    ),
    "security-review": Macro(
        task=SECURITY_REVIEW_PROMPT.format(argument=SECURITY_REVIEW_DEFAULT_SCOPE),
        template=SECURITY_REVIEW_PROMPT,
    ),
    "debug": Macro(
        task="Fusion'ın bu oturumdaki davranışını teşhis et: `fusion doctor --json` "
        "komutunu çalıştır, `recent_actions` ile son eylemleri ve hataları incele, "
        "kullanıcının gördüğü belirtiyi bunlarla eşleştir. Kök nedeni (yapılandırma, "
        "model, izin kipi, sağlayıcı, MCP) ve somut düzeltme adımını söyle. Proje "
        "kodunu değiştirme; sırları raporda yazma.",
        template="Fusion'ın şu sorununu teşhis et: {argument}. `fusion doctor --json` "
        "komutunu çalıştır, `recent_actions` ile son eylemleri ve hataları incele, "
        "belirtiyi bunlarla eşleştir; kök nedeni ve somut düzeltme adımını söyle. Proje "
        "kodunu değiştirme; sırları raporda yazma.",
    ),
    "batch": Macro(
        task="",
        template="Şu talimatı kod tabanının tamamına uygula: {argument}. Önce etkilenen "
        "dosyaları bul ve işi birbirinden bağımsız 3-10 parçaya böl (dosya ya da klasör "
        "kümesi). Her parçayı `spawn_agents` ile PARALEL alt ajanlara ver; her ajanın "
        "`yazma_alani` değerini yalnız kendi dosyalarıyla sınırla ki iki ajan aynı "
        "dosyaya dokunmasın. Ajanlar bitince sonuçları birleştir, testleri koştur ve "
        "parça parça özetle.",
        argument_required=True,
    ),
}


#: `/skills new <ad>` — beceri dosyasını modele yazdıran görev (Claude Code `/skills new`).
SKILL_NEW_TASK = (
    "Yeni bir beceri (SKILL.md) oluştur: `.claude/skills/{name}/SKILL.md`. Önce `ask_user` ile "
    "iki kısa soru sor: (1) beceri ne zaman kullanılacak ve ne yapacak, (2) hangi araçlara "
    "ihtiyacı var (dosya/komut/web). Sonra dosyayı yaz: ön madde `name: {name}`, `description` "
    "(ne yaptığı + ne zaman kullanılacağı, tek cümle, 150 karakteri geçmesin), gerekiyorsa "
    "`allowed-tools` ve `argument-hint`; gövde adım adım talimat, `$ARGUMENTS` yer tutucusu. "
    "Mevcut dosyanın üzerine yazma; varsa kullanıcıya sor. Bitince `/skills reload` demesini "
    "hatırlat."
)

#: `/agents new <ad>` — uzman ajan dosyasını modele yazdıran görev (Claude Code `/agents`).
AGENT_NEW_TASK = (
    "Yeni bir uzman ajan tanımı oluştur: `.claude/agents/{name}.md`. Önce `ask_user` ile sor: "
    "(1) uzmanlık alanı ve görevi, (2) kapsam (yalnız bu proje mi, `~/.claude/agents` altında "
    "genel mi), (3) araç kısıtı (salt-okur mu, komut çalıştırır mı). Sonra dosyayı yaz: ön "
    "madde `name: {name}`, `description` (hangi işte devreye girer), `tools` (ör. Read, Grep, "
    "Bash); gövde ajanın sistem talimatı: rol, çalışma biçimi, çıktı biçimi. Mevcut dosyanın "
    "üzerine yazma; varsa kullanıcıya sor."
)


def get(name: str) -> Macro | None:
    return MACROS.get(name)


def mode_prompt(mode: Mode) -> str:
    """Kipin sistem promptuna eklenecek metni; kip yoksa boş."""
    return MODE_PROMPTS.get(mode, "")


def mode_step_limit(mode: Mode) -> int | None:
    """Kipin adım sınırı; kip sınır değiştirmiyorsa None (varsayılan bütçe)."""
    return MODE_STEP_LIMITS.get(mode)


def mode_workflow(mode: Mode) -> bool:
    """Kip bu turu plan motorunda yürütmeyi mi istiyor?"""
    return mode is Mode.WORKFLOW
