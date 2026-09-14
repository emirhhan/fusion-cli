# DomainAdapter v2 (2a) — Uygulama Planı

> **Ajanlar için:** ZORUNLU ALT BECERİ: superpowers:subagent-driven-development (önerilen) veya
> superpowers:executing-plans ile görev görev uygulanır. Adımlar `- [ ]` ile işaretlenir.

**Kaynak:** `FUSION_MASTER_PROJE_DOKUMANI.md` §2, §4.5, §5.12, §10, §13.1, §14 "Faz 1 — DomainAdapter v2
ve genel kanıt paketi", §15, §16/1-2. Kod okuması 14 Eylül 2026, HEAD `5ef1453`,
dal `fusion-runtime-hardening-20260827-022831`.

**Amaç:** Godot'a özel olgunluğu (kapılar, sıfır-çıkış işaretleri, çapraz dosya denetimleri, kabul
koşulları, oyun teslimatları) motorun içinden çıkarıp tek bir **alan kayıt defterine** bağlamak;
Godot davranışını bir milim bile gevşetmeden, yeni bir alan eklemenin motor dosyasına dokunmadan
yapılabildiğini testle kanıtlamak.

**Kodda doğrulanan bugünkü durum:**

1. `engines/agent/domains.py::adapter_for` üretimde hiç çağrılmıyor (yalnız testler).
   `DomainAdapter.acceptance_criteria()` hiçbir plan istemine girmiyor.
2. `verify_discovery.py::_godot` kayıt yerine `godot_adapter()`'ı doğrudan çağırıyor.
3. `verification.py::_ZERO_EXIT_FAILURE_MARKERS` modül-global; yalnız Godot'tan kuruluyor.
4. `step_verification.py::verify_plan_acceptance` altı Godot çapraz denetimini (`core/cross_file.py`)
   HER projede doğrudan çağırıyor.
5. `plan_generation.py::generate_plan` alan bilgisi olmadan `missing_deliverables()` kullanıyor;
   `plan_coverage.py::DELIVERABLES` "düşman ve dövüş" ile "hikâye / ara sahne"yi global tutuyor.
6. `loop.py::_repeated_failure_note` ve tekrar notu iki kullanıcı metninde `'res://'` örneği taşıyor
   (MCP araç hatası ipucu) — bu plan onu taşımaz, mimari testte sayılı borç olarak kilitler.

**Mimari:** `engines/agent/domain_adapters/` paketi eklenir: `contract.py` (DomainAdapter v2 +
`ToolFailureMarkers`), `registry.py` (değişmez `DomainRegistry`), `godot.py`, `web.py`,
`defaults.py` (`default_domain_registry()` fabrikası). Kayıt defteri modül-global DEĞİLDİR:
`AgentDeps.domains` alanıyla (`default_factory`) ve `build_verifier`/`discover_*`/`CommandVerifier`
parametreleriyle enjekte edilir. `domains.py` geriye uyumlu yeniden-dışa-açma modülü olarak kalır.

**Teknoloji:** Python 3.11+, pytest (asyncio auto), ruff, mypy strict.

## Genel Kısıtlar

- `CLAUDE.md` ve `RULES.md` bağlayıcıdır; deponun `.env` dosyası OKUNMAZ.
- Dal: `fusion-runtime-hardening-20260827-022831`; yeni dal açılmaz, dal değiştirilmez, push YOK.
- İzlenmeyen kullanıcı dosyalarına dokunulmaz: `:memory:.ses`, `dagitim/`, `index.html`,
  `FUSION_MASTER_PROJE_DOKUMANI.md`. `git add` her zaman dosya adıyla yapılır (`git add -A` YOK).
- Docstring, yorum, hata ve prompt metinleri Türkçe; tanımlayıcılar İngilizce (PEP 8).
- `core` stdlib dışında import etmez; `tools` → `engines` importu açılmaz. `core/structured_files.py`
  içindeki Godot biçim kuralları bu planda YERİNDE kalır (yazma yolu `tools/files.py` kullanıyor).
- Adaptör sözleşmesi plan yürütmesine, onaya, bütçeye veya `AgentDeps`'e kanca VERMEZ; tüm kancalar
  yalnız `Path` (ve görev metni) alır ve metin/komut döndürür.
- Korunacak davranışlar (her görev bunları kırmadığını tam test paketiyle gösterir):
  - Keşif sırası Python → Node → **alan kapıları (Godot'un bugünkü yeri)** → Rust → Go → Make; ilk boş
    olmayan kazanır.
  - Otomatik Node kapısı yalnız `typecheck`/`build`.
  - `project_kinds()` alfabetik; tüketicileri (`learning_steps`, `project_instructions.workspace_summary`,
    `memory.lessons`) değişmez. `_KIND_MARKERS` bu planda dokunulmaz.
  - Sıfır-çıkış işaret taraması proje işaretinden BAĞIMSIZDIR (komutta araç adı geçiyorsa çalışır).
  - Ana sahne dosyasının diskte varlığı; içe aktarma hazırlığının davranış kapısından önce gelmesi;
    kurulum kapısına düşüş.
  - Çapraz dosya denetimleri `project.godot` yokken de (`.gd/.tscn/.tres` varsa) çalışır.
  - Proje açılışı davranış kanıtı sayılmaz; eksik komut → `ok=True` + `UNVERIFIED` + uyarı.
- Kalite kapısı (her commit öncesi, üçü de temiz): `.venv/bin/ruff check .`, `.venv/bin/mypy`,
  `.venv/bin/pytest -q`.
- Commit: Türkçe conventional commit; faz/görev numarası YOK, co-author satırı YOK.
- Mevcut bir test kırılırsa test gevşetilmez: davranış farkı raporlanır ve kök neden düzeltilir.

## Tasarım kararları

| Karar | Gerekçe |
|---|---|
| **Çok alanlı projede eşleşen TÜM adaptörler uygulanır** (kayıt sırasıyla, komutlar tekrarsız birleşir). | Meshy→Blender→Godot zinciri tek dizinde `.blend` + `project.godot` taşır. "İlk eşleşen kazanır" ikinci alanın kapısını SESSİZCE düşürürdü — tam da bu platformun önlemek istediği hata sınıfı. `adapter_for` geriye uyum için ilk eşleşeni döndürmeye devam eder. |
| Keşifte alan kapıları tek bir yuvada (Node ile Rust arası) çalışır. | Bugünkü `_godot` yeri; sıra ve "ilk boş olmayan kazanır" birebir korunur. |
| Sıfır-çıkış işaretleri **kayıttaki tüm adaptörlerden** gelir, eşleşmeden değil; anahtar `executable`. | Bugünkü testler Godot çıktısını `project.godot` olmadan üretiyor; işaret, projenin değil ÇALIŞAN ARACIN özelliğidir. |
| Artifact denetimi: adaptör kökte eşleşirse **veya** `artifact_suffixes` uzantılı bir dosya ağaçta varsa çalışır. | `core/cross_file.py` bugün `rglob` ile tüm ağacı tarıyor ve `project.godot` şartı yok; Godot uzantıları (`.gd/.tscn/.tres`) + işaret, altı denetimin baktığı dosya kümesinin tamamını kapsar → çıktı birebir aynı. |
| Kabul koşulları planlamaya **ilgili** adaptörlerden verilir: kökte eşleşen **veya** görevde `task_markers` kelime sınırıyla geçen. | Boş dizinde "Godot ile oyun yap" isteğinde kök işareti henüz yok. Kelime sınırı (`(?<!\w)…(?!\w)`) alt-dize yanlış pozitiflerini (`godotengine`, `xhtml`, `webhook`) önler. `oyun`/`game` Godot işareti DEĞİLDİR: tarayıcı oyununa Godot koşulu girmez. |
| Alan teslimatları (düşman/dövüş, hikâye/ara sahne) **kayıttaki tüm adaptörlerden** toplanır. | Teslimatın kendi `request_markers` alanı zaten "açıkça istendi mi" kapısıdır; eşleşmeye bağlamak boş dizindeki Dead Cells isteğinde düşman adımını düşürürdü (koşu 32'nin hatası geri gelirdi). Sahiplik Godot paketine geçer, davranış aynı kalır. |
| Web artifact denetimi yalnız kökteki `index.html`'in GÖRELİ yerel kaynaklarını ölçer. | Kök-mutlak yollar (`/src/main.tsx`, `/favicon.ico`) sunucu/paketleyiciye göre (`public/`) çözülür; iddia edilemez. `package.json` tek başına web kanıtı sayılmaz (işaret `index.html`). `WebVerifier` değişmez. |
| Parametreler `domains: DomainRegistry | None = None` → `None` iken `default_domain_registry()` o anda kurulur. | Kayıt değişmez değer nesnesidir; iki varsayılan örnek eşittir, ayrışma riski yoktur. Böylece CLI/REPL/eval çağrı yerleri ve ~20 mevcut test değişmeden kalır; sahte kayıt vermek isteyen açıkça geçer. |

---

### Görev 0: Başlangıç durumunu kaydet

**Dosyalar:** yok (salt okuma).

- [ ] **Adım 1: Dal, HEAD ve çalışma ağacını kaydet**

Run:
```bash
cd /Users/motogate/Desktop/01-Projeler/fusion-cli
git branch --show-current
git rev-parse --short HEAD
git status --short
```
Expected: `fusion-runtime-hardening-20260827-022831`, `5ef1453` (ya da kullanıcının sonraki commit'i),
yalnız izlenmeyen `:memory:.ses`, `FUSION_MASTER_PROJE_DOKUMANI.md`, `dagitim/`, `index.html`.
Beklenenden farklı değişiklik varsa DUR ve kullanıcıya sor.

- [ ] **Adım 2: Temel kalite kapısını çalıştır**

Run: `.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest -q`
Expected: üçü de temiz. Kırmızıysa bu planın işi değildir; DUR ve kırılan testleri kullanıcıya bildir.

---

### Görev 1: Alan adaptörü sözleşmesi ve kayıt defteri

**Dosyalar:**
- Create: `src/fusion_cli/engines/agent/domain_adapters/__init__.py`
- Create: `src/fusion_cli/engines/agent/domain_adapters/contract.py`
- Create: `src/fusion_cli/engines/agent/domain_adapters/registry.py`
- Test: `tests/test_domain_registry.py`

**Arayüzler:**
- Tüketir: `fusion_cli.engines.agent.plan_coverage.Deliverable` (mevcut, değişmez),
  `fusion_cli.core.errors.FusionError`.
- Üretir:
  - `ToolFailureMarkers(tool: str, markers: tuple[str, ...])` — frozen dataclass.
  - `DomainAdapter(name, marker, gates=(), setup_gates=(), is_runnable=None, preparation=None,
    executable="", output_failure_markers=(), criteria=(), task_markers=(), artifact_suffixes=(),
    artifact_checks=(), deliverables=())` — frozen; metotlar `matches(root) -> bool`,
    `gate_commands(root) -> tuple[str, ...]`, `zero_exit_failure_markers() -> tuple[str, ...]`,
    `acceptance_criteria() -> tuple[str, ...]`, `is_named_in(task: str) -> bool`,
    `applies_to_artifacts(root) -> bool`, `artifact_findings(root) -> tuple[str, ...]`.
  - `DomainRegistry(adapters: tuple[DomainAdapter, ...])` — frozen; metotlar
    `matching(root)`, `first_match(root) -> DomainAdapter | None`, `relevant(root, task)`,
    `gate_commands(root) -> tuple[str, ...]`, `output_failure_markers() -> tuple[ToolFailureMarkers, ...]`,
    `artifact_findings(root) -> tuple[str, ...]`, `acceptance_criteria(root, task) -> tuple[str, ...]`,
    `deliverables() -> tuple[Deliverable, ...]`. Aynı adlı iki adaptör `FusionError`.

- [ ] **Adım 1: Başarısız testi yaz**

`tests/test_domain_registry.py`:
```python
"""Alan kayıt defteri: yeni alan eklemek motoru değiştirmeden adaptör eklemektir.

Kayıt defteri alanların kanıt sözleşmelerini birleştirir; hangi alanın ne istediğini
motor bilmez. Çok alanlı projede (ör. `.blend` + `project.godot`) eşleşen TÜM alanlar
uygulanır: birini seçmek diğerinin kapısını sessizce düşürürdü.
"""

from __future__ import annotations

from dataclasses import fields

import pytest

from fusion_cli.core.errors import FusionError
from fusion_cli.engines.agent.domain_adapters.contract import DomainAdapter, ToolFailureMarkers
from fusion_cli.engines.agent.domain_adapters.registry import DomainRegistry
from fusion_cli.engines.agent.plan_coverage import Deliverable


def test_birden_cok_alan_eslesirse_hepsi_kayit_sirasiyla_doner(tmp_path):
    (tmp_path / "sahne.blend").write_text("", encoding="utf-8")
    (tmp_path / "medya.json").write_text("{}", encoding="utf-8")
    blender = DomainAdapter(name="blender", marker="sahne.blend")
    web = DomainAdapter(name="web", marker="index.html")
    medya = DomainAdapter(name="medya", marker="medya.json")
    kayit = DomainRegistry((blender, web, medya))

    assert kayit.matching(tmp_path) == (blender, medya)
    assert kayit.first_match(tmp_path) is blender


def test_eslesen_alanlarin_kapilari_sirayla_ve_tekrarsiz_birlesir(tmp_path):
    (tmp_path / "sahne.blend").write_text("", encoding="utf-8")
    (tmp_path / "medya.json").write_text("{}", encoding="utf-8")
    kayit = DomainRegistry(
        (
            DomainAdapter(
                name="blender",
                marker="sahne.blend",
                gates=("blender --background --quit", "ortak-kontrol"),
            ),
            DomainAdapter(
                name="medya", marker="medya.json", gates=("ffprobe cikti.mp4", "ortak-kontrol")
            ),
        )
    )

    assert kayit.gate_commands(tmp_path) == (
        "blender --background --quit",
        "ortak-kontrol",
        "ffprobe cikti.mp4",
    )


def test_calistirilamayan_projede_kurulum_kapisi_secilir(tmp_path):
    """Hazırlık yalnız çalıştırılabilir projede ve davranış kapısından ÖNCE gelir."""
    durum = {"hazir": False}
    adaptor = DomainAdapter(
        name="blender",
        marker="sahne.blend",
        gates=("blender --render",),
        setup_gates=("blender --version",),
        is_runnable=lambda kok: durum["hazir"],
        preparation=lambda kok: ("blender --hazirla",),
    )

    assert adaptor.gate_commands(tmp_path) == ("blender --version",)

    durum["hazir"] = True

    assert adaptor.gate_commands(tmp_path) == ("blender --hazirla", "blender --render")


def test_cikti_isaretleri_yalniz_calistirilabilir_adi_olan_alandan_gelir():
    kayit = DomainRegistry(
        (
            DomainAdapter(
                name="blender",
                marker="sahne.blend",
                executable="blender",
                output_failure_markers=("error: python",),
            ),
            DomainAdapter(name="web", marker="index.html", output_failure_markers=("uncaught",)),
        )
    )

    assert kayit.output_failure_markers() == (ToolFailureMarkers("blender", ("error: python",)),)


def test_artifact_denetimi_isaret_yokken_de_uzantiyla_calisir(tmp_path):
    cagrilar: list[object] = []

    def denetim(kok):
        cagrilar.append(kok)
        return ("çıktı eksik",)

    kayit = DomainRegistry(
        (
            DomainAdapter(
                name="medya",
                marker="medya.json",
                artifact_suffixes=(".mp4",),
                artifact_checks=(denetim,),
            ),
        )
    )

    assert kayit.artifact_findings(tmp_path) == ()
    assert cagrilar == []

    (tmp_path / "klip").mkdir()
    (tmp_path / "klip" / "a.mp4").write_bytes(b"x")

    assert kayit.artifact_findings(tmp_path) == ("çıktı eksik",)


def test_kabul_kosullari_kokten_ya_da_gorevde_kelime_olarak_gecen_alandan_gelir(tmp_path):
    kayit = DomainRegistry(
        (
            DomainAdapter(
                name="blender",
                marker="sahne.blend",
                criteria=("render dosyası üretildi",),
                task_markers=("blender",),
            ),
        )
    )

    assert kayit.acceptance_criteria(tmp_path, "bir logo çiz") == ()
    assert kayit.acceptance_criteria(tmp_path, "Blender'da sahne kur") == (
        "render dosyası üretildi",
    )
    assert kayit.acceptance_criteria(tmp_path, "blenderbot ile konuş") == ()

    (tmp_path / "sahne.blend").write_text("", encoding="utf-8")

    assert kayit.acceptance_criteria(tmp_path, "bir logo çiz") == ("render dosyası üretildi",)


def test_teslimatlar_tum_alanlardan_ad_tekrarsiz_toplanir():
    render = Deliverable(
        name="render",
        request_markers=("render",),
        plan_markers=("render",),
        instruction="render dosyasını üreten ayrı bir adım",
    )
    kayit = DomainRegistry(
        (
            DomainAdapter(name="a", marker="a.x", deliverables=(render,)),
            DomainAdapter(name="b", marker="b.x", deliverables=(render,)),
        )
    )

    assert kayit.deliverables() == (render,)


def test_ayni_adli_iki_alan_reddedilir():
    with pytest.raises(FusionError, match="blender"):
        DomainRegistry(
            (
                DomainAdapter(name="blender", marker="a.blend"),
                DomainAdapter(name="blender", marker="b.blend"),
            )
        )


def test_adaptor_sozlesmesi_plan_ve_onaya_kanca_vermez():
    """Adaptör YALNIZ kanıt sözleşmesidir.

    Plan yürütmesine, onaya veya bütçeye kanca eklemek bu testi bilinçli olarak
    değiştirmeyi gerektirir: bir alanın ortak güvenlik politikasını ezmesi sessizce
    mümkün olmamalı (master belge §14 Faz 1).
    """
    assert {alan.name for alan in fields(DomainAdapter)} == {
        "name",
        "marker",
        "gates",
        "setup_gates",
        "is_runnable",
        "preparation",
        "executable",
        "output_failure_markers",
        "criteria",
        "task_markers",
        "artifact_suffixes",
        "artifact_checks",
        "deliverables",
    }
```

- [ ] **Adım 2: Testin düştüğünü gör**

Run: `.venv/bin/pytest tests/test_domain_registry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.engines.agent.domain_adapters'`.

- [ ] **Adım 3: Paketi ve sözleşmeyi yaz**

`src/fusion_cli/engines/agent/domain_adapters/__init__.py`:
```python
"""Alan adaptörleri: sözleşme, kayıt defteri ve alan paketleri.

Motor değişmez; bir işin BİTTİĞİNİ neyin kanıtladığı alana göre değişir. Yeni alan
eklemek bu pakete bir adaptör yazıp kayıt defterine eklemektir.
"""
```

`src/fusion_cli/engines/agent/domain_adapters/contract.py`:
```python
"""Alan adaptörü sözleşmesi — "neyin kanıt sayıldığı" alana göre tanımlanır.

Motor değişmez: plan, kanıt, onay, kurtarma ve bütçe her alanda aynı çalışır. Değişen
şey bir işin BİTTİĞİNİ neyin kanıtladığıdır: Godot'ta "proje açılıyor + hata basmıyor
+ ana sahne diskte"; web'de "sayfanın yerel kaynakları var"; medyada "çıktı dosyası
gerçek".

Adaptör YALNIZ kanıt sözleşmesini tanımlar, akışı tanımlamaz. Her kanca yalnız bir
kök dizin (ya da görev metni) alır ve komut/bulgu/metin döndürür; plan yürütmesine,
onaya veya bütçeye erişimi yoktur. Motorun kurallarını ezmeye başlarsa tek sözleşme
bozulur.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..plan_coverage import Deliverable

#: Kökten engelleyici bulgu üreten denetim; boş demet "sorun yok" demektir.
ArtifactCheck = Callable[[Path], tuple[str, ...]]
#: Kök hakkında evet/hayır cevabı veren ölçüt (ör. "proje çalıştırılabilir mi").
RootPredicate = Callable[[Path], bool]
#: Kapıdan ÖNCE çalışması gereken hazırlık komutlarını üreten kanca.
PreparationCommands = Callable[[Path], tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class ToolFailureMarkers:
    """Sıfır çıkış koduna rağmen hatayı ele veren çıktı işaretleri.

    Anahtar ÇALIŞAN ARACIN adıdır, proje işareti değil: motor hatayı basıp `0`
    döndürüyorsa bu, proje dizininde ne olduğundan bağımsız olarak doğrudur.
    """

    tool: str
    markers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DomainAdapter:
    """Bir alanın kanıt sözleşmesi."""

    name: str
    #: Bu dizin bu alana ait mi? (kökte varlığı aranan dosya)
    marker: str
    #: Projenin DAVRANIŞINI ölçen kapı komutları.
    gates: tuple[str, ...] = ()
    #: Proje HENÜZ çalıştırılabilir değilken kullanılan ucuz ve dönmesi garanti kapı.
    setup_gates: tuple[str, ...] = ()
    #: Projenin çalıştırılabilir hâle gelip gelmediğini söyleyen ölçüt.
    is_runnable: RootPredicate | None = None
    #: Davranış kapısından önce çalışacak hazırlık komutları.
    preparation: PreparationCommands | None = None
    #: Kapının çalıştırdığı aracın komut satırındaki adı (işaret taraması anahtarı).
    executable: str = ""
    #: Çıkış kodu sıfır olsa bile hatayı ele veren küçük harfli çıktı parçaları.
    output_failure_markers: tuple[str, ...] = ()
    #: Planlayıcıya verilecek, alana özgü kabul koşulları.
    criteria: tuple[str, ...] = ()
    #: Görev metninde bu alanı adıyla anan kelimeler (kelime sınırıyla aranır).
    task_markers: tuple[str, ...] = ()
    #: Kök işareti yokken de artifact denetimini tetikleyen dosya uzantıları.
    artifact_suffixes: tuple[str, ...] = ()
    #: Final kabulde çalışan, motor koşmadan sessiz hatayı söyleyen denetimler.
    artifact_checks: tuple[ArtifactCheck, ...] = ()
    #: Görevde açıkça istenirse planın adıyla karşılaması gereken alan teslimatları.
    deliverables: tuple[Deliverable, ...] = ()

    def matches(self, root: Path) -> bool:
        """Kök dizin bu alanın işaret dosyasını taşıyor mu?"""
        return (root / self.marker).exists()

    def gate_commands(self, root: Path) -> tuple[str, ...]:
        """Projenin AÇILDIĞINI/çalıştığını kanıtlayan komutlar.

        Kapı projenin O ANKİ durumuna göre seçilir. Ölçüldü (7 Eylül canlı koşusu,
        `project-setup`): yarım kurulmuş projede davranış kapısı hatayı basıp ASILI
        KALDI; 120 saniye beklendi, adım zaman aşımıyla düştü ve kurtarma hakkı
        tükendi. Kurulum aşamasında kapı ucuz ve dönmesi GARANTİ olmalı; proje
        çalıştırılabilir olur olmaz yine davranışı ölçer.
        """
        preparation = self.preparation(root) if self.preparation is not None else ()
        if self.is_runnable is None or not self.setup_gates or self.is_runnable(root):
            return preparation + self.gates
        return self.setup_gates

    def zero_exit_failure_markers(self) -> tuple[str, ...]:
        """Çıkış kodu sıfır olsa bile hatayı ele veren çıktı işaretleri."""
        return self.output_failure_markers

    def acceptance_criteria(self) -> tuple[str, ...]:
        """Planlayıcıya verilecek, alana özgü kabul koşulları."""
        return self.criteria

    def is_named_in(self, task: str) -> bool:
        """Görev bu alanı adıyla anıyor mu? Alt-dize değil, kelime eşleşmesi aranır.

        `godot` kelimesi `godotengine` içinde, `html` kelimesi `xhtml` içinde
        EŞLEŞMEZ; `Godot'ta` gibi kesme işaretli Türkçe ekler eşleşir.
        """
        lowered = task.casefold()
        return any(_contains_word(lowered, marker.casefold()) for marker in self.task_markers)

    def applies_to_artifacts(self, root: Path) -> bool:
        """Artifact denetimleri bu kökte çalışmalı mı?

        Kök işareti yokken de alanın dosyaları ağaçta durabilir (ör. `project.godot`
        henüz yazılmamışken sahne ve script). O durumda denetim atlanırsa sessiz
        hata sınıfı teslime kadar gelir.
        """
        if self.matches(root):
            return True
        return any(
            next(root.rglob(f"*{suffix}"), None) is not None for suffix in self.artifact_suffixes
        )

    def artifact_findings(self, root: Path) -> tuple[str, ...]:
        """Alanın artifact denetimlerinin engelleyici bulguları, denetim sırasıyla."""
        if not self.artifact_checks or not self.applies_to_artifacts(root):
            return ()
        return tuple(finding for check in self.artifact_checks for finding in check(root))


def _contains_word(text: str, phrase: str) -> bool:
    """`phrase` metinde iki yanında harf/rakam olmadan geçiyor mu?"""
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None
```

`src/fusion_cli/engines/agent/domain_adapters/registry.py`:
```python
"""Alan kayıt defteri — kayıtlı adaptörlerin kanıt sözleşmelerini birleştirir.

Kayıt defteri DEĞİŞMEZ bir değer nesnesidir ve modül seviyesinde tutulmaz; çağıran
onu kurucu/parametre yoluyla verir (RULES.md "Bağımlılık ve Soyutlama").

Çok alanlı projede eşleşen TÜM adaptörler uygulanır. Ölçüt: Meshy → Blender → Godot
zinciri aynı dizinde `.blend` ve `project.godot` taşır; "ilk eşleşen kazanır" ikinci
alanın kapısını sessizce düşürürdü.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ....core.errors import FusionError
from ..plan_coverage import Deliverable
from .contract import DomainAdapter, ToolFailureMarkers


@dataclass(frozen=True, slots=True)
class DomainRegistry:
    """Kayıtlı alan adaptörleri, kayıt sırasıyla."""

    adapters: tuple[DomainAdapter, ...]

    def __post_init__(self) -> None:
        names = [adapter.name for adapter in self.adapters]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise FusionError(
                "Alan adaptörü adları tekil olmalı; tekrar eden: "
                + ", ".join(duplicates)
                + ". Her alanı kayıt defterine bir kez ekleyin."
            )

    def matching(self, root: Path) -> tuple[DomainAdapter, ...]:
        """Kökte işareti bulunan adaptörler, kayıt sırasıyla."""
        return tuple(adapter for adapter in self.adapters if adapter.matches(root))

    def first_match(self, root: Path) -> DomainAdapter | None:
        """Kökte eşleşen ilk adaptör; yoksa `None` (geriye uyumlu tekil sorgu)."""
        return next((adapter for adapter in self.adapters if adapter.matches(root)), None)

    def relevant(self, root: Path, task: str) -> tuple[DomainAdapter, ...]:
        """Kökte eşleşen ya da görevde adıyla anılan adaptörler."""
        return tuple(
            adapter
            for adapter in self.adapters
            if adapter.matches(root) or adapter.is_named_in(task)
        )

    def gate_commands(self, root: Path) -> tuple[str, ...]:
        """Eşleşen tüm alanların kapı komutları; sıra korunur, tekrar atılır."""
        return _unique(
            command for adapter in self.matching(root) for command in adapter.gate_commands(root)
        )

    def output_failure_markers(self) -> tuple[ToolFailureMarkers, ...]:
        """Kayıttaki TÜM alanların sıfır-çıkış işaretleri, araç adına göre.

        Eşleşmeye bağlı değildir: işaret, projenin değil çalışan aracın özelliğidir.
        """
        return tuple(
            ToolFailureMarkers(adapter.executable, adapter.output_failure_markers)
            for adapter in self.adapters
            if adapter.executable and adapter.output_failure_markers
        )

    def artifact_findings(self, root: Path) -> tuple[str, ...]:
        """Uygulanan alanların artifact bulguları; sıra korunur, tekrar atılır."""
        return _unique(
            finding for adapter in self.adapters for finding in adapter.artifact_findings(root)
        )

    def acceptance_criteria(self, root: Path, task: str) -> tuple[str, ...]:
        """Plan istemine girecek, ilgili alanların kabul koşulları."""
        return _unique(
            criterion
            for adapter in self.relevant(root, task)
            for criterion in adapter.acceptance_criteria()
        )

    def deliverables(self) -> tuple[Deliverable, ...]:
        """Kayıttaki tüm alanların teslimatları; aynı ad bir kez.

        Eşleşmeye bağlanmaz: teslimatın `request_markers` alanı zaten "görevde açıkça
        istendi mi" kapısıdır. Boş dizindeki bir oyun isteğinde kök işareti henüz
        yoktur ve eşleşmeye bağlamak istenen teslimatı sessizce düşürürdü.
        """
        seen: set[str] = set()
        collected: list[Deliverable] = []
        for adapter in self.adapters:
            for deliverable in adapter.deliverables:
                if deliverable.name not in seen:
                    seen.add(deliverable.name)
                    collected.append(deliverable)
        return tuple(collected)


def _unique(items: object) -> tuple[str, ...]:
    """Metinleri ilk görülme sırasıyla tekrarsız demete çevir."""
    return tuple(dict.fromkeys(items))  # type: ignore[call-overload]
```

> Not: `_unique` için `object` + `type: ignore` KULLANMA; aşağıdaki tipli sürümü yaz (RULES: gerekçesiz
> bastırma yok). Yukarıdaki bloğun son fonksiyonunu şu hâliyle kaydet:

```python
from collections.abc import Iterable


def _unique(items: Iterable[str]) -> tuple[str, ...]:
    """Metinleri ilk görülme sırasıyla tekrarsız demete çevir."""
    return tuple(dict.fromkeys(items))
```
(`from collections.abc import Iterable` satırı dosyanın import bloğuna, `from dataclasses import dataclass`
satırının üstüne taşınır.)

- [ ] **Adım 4: Testin geçtiğini gör**

Run: `.venv/bin/pytest tests/test_domain_registry.py -q`
Expected: 9 passed.

- [ ] **Adım 5: Kalite kapısı**

Run: `.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest -q`
Expected: üçü temiz.

- [ ] **Adım 6: Commit**

```bash
git add src/fusion_cli/engines/agent/domain_adapters/__init__.py \
  src/fusion_cli/engines/agent/domain_adapters/contract.py \
  src/fusion_cli/engines/agent/domain_adapters/registry.py \
  tests/test_domain_registry.py
git commit -m "feat(alan): alan adaptörü sözleşmesi ve değişmez kayıt defteri"
```

---

### Görev 2: Godot ve web adaptörlerini alan paketine taşı

**Dosyalar:**
- Create: `src/fusion_cli/engines/agent/domain_adapters/godot.py`
- Create: `src/fusion_cli/engines/agent/domain_adapters/web.py`
- Create: `src/fusion_cli/engines/agent/domain_adapters/defaults.py`
- Modify (tamamen yeniden yazılır): `src/fusion_cli/engines/agent/domains.py`
- Test: `tests/test_domain_defaults.py` (mevcut `tests/test_domains.py`, `tests/test_domain_adapters.py`,
  `tests/test_godot_setup_gate.py` DEĞİŞMEDEN geçmeli — geriye uyum kanıtı)

**Arayüzler:**
- Tüketir: Görev 1 `DomainAdapter`, `DomainRegistry`.
- Üretir: `godot_adapter() -> DomainAdapter`, `godot_has_main_scene(root) -> bool`,
  `godot_needs_import(root) -> bool` (`domain_adapters/godot.py`); `web_adapter() -> DomainAdapter`
  (`domain_adapters/web.py`); `default_domain_registry() -> DomainRegistry` (godot, web sırasıyla);
  `domains.py` aynı adları + `DomainAdapter` + `adapter_for(root)` dışa açar.

- [ ] **Adım 1: Başarısız testi yaz**

`tests/test_domain_defaults.py`:
```python
"""Varsayılan alan kaydı ve eski `domains` içe aktarmalarının geriye uyumu.

Godot bilgisi motordan alan paketine taşınırken tek bir davranış değişmemeli: eski
içe aktarma yolları aynı adaptörü vermeli, keşif ve kapı sırası aynı kalmalı.
"""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.domain_adapters.defaults import default_domain_registry
from fusion_cli.engines.agent.domain_adapters.godot import godot_adapter
from fusion_cli.engines.agent.domain_adapters.web import web_adapter


def test_varsayilan_kayit_godot_ve_web_alanlarini_sirayla_icerir():
    assert tuple(adaptor.name for adaptor in default_domain_registry().adapters) == ("godot", "web")


def test_iki_varsayilan_kayit_esittir():
    """Kayıt değer nesnesidir: ayrı kurulan iki varsayılan örnek ayrışamaz."""
    assert default_domain_registry() == default_domain_registry()


def test_eski_domains_iceri_aktarmalari_ayni_adaptoru_verir():
    from fusion_cli.engines.agent import domains
    from fusion_cli.engines.agent.domain_adapters import godot

    assert domains.godot_adapter() == godot_adapter()
    assert domains.web_adapter() == web_adapter()
    assert domains.godot_has_main_scene is godot.godot_has_main_scene
    assert domains.godot_needs_import is godot.godot_needs_import


def test_godot_ve_web_birlikte_eslesirse_adapter_for_godotu_secer(tmp_path):
    from fusion_cli.engines.agent.domains import adapter_for

    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")

    adaptor = adapter_for(tmp_path)

    assert adaptor is not None
    assert adaptor.name == "godot"


def test_godot_calistirilabilir_adi_isaret_taramasinin_anahtaridir():
    assert godot_adapter().executable == "godot"


@pytest.mark.parametrize(
    ("gorev", "beklenen"),
    [
        ("Godot'ta platform oyunu yap", True),
        ("GDScript hatasını düzelt", True),
        ("main.tscn sahnesine düğüm ekle", True),
        ("godotengine.org sürüm notlarını özetle", False),
        ("tarayıcıda çalışan bir oyun yap", False),
        ("Dead Cells benzeri bir oyun istiyorum", False),
    ],
)
def test_godot_gorev_isaretleri_alt_dizeyle_tetiklenmez(gorev, beklenen):
    assert godot_adapter().is_named_in(gorev) is beklenen


@pytest.mark.parametrize(
    ("gorev", "beklenen"),
    [
        ("basit bir HTML sayfası yap", True),
        ("şirket için web sitesi kur", True),
        ("ürün için landing page tasarla", True),
        ("webhook ekle", False),
        ("XHTML ayrıştırıcısını düzelt", False),
        ("web API'si yaz", False),
    ],
)
def test_web_gorev_isaretleri_alt_dizeyle_tetiklenmez(gorev, beklenen):
    assert web_adapter().is_named_in(gorev) is beklenen
```

- [ ] **Adım 2: Testin düştüğünü gör**

Run: `.venv/bin/pytest tests/test_domain_defaults.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fusion_cli.engines.agent.domain_adapters.defaults'`.

- [ ] **Adım 3: Godot adaptör modülünü yaz**

`src/fusion_cli/engines/agent/domain_adapters/godot.py` (içerik `domains.py`'dan birebir taşınır; tek
fark alan adları ve `executable`/`task_markers`):
```python
"""Godot alanı — motorun kendisi projeyi açabiliyor mu, hata basıyor mu?

Ölçüldü (5-6 Eylül): Godot bozuk script'te ve çalışma zamanı hatasında `0` çıkış
kodu verebiliyor; "açıldı" ile "hatasız açıldı" ayrı şeylerdir. Bu modül Godot'a
özgü tüm kanıt bilgisini tek yerde tutar; motor bu adları hiç bilmez.
"""

from __future__ import annotations

import re
from pathlib import Path

from ....core.constants import SKIP_DIRECTORIES
from .contract import DomainAdapter

#: `project.godot` içinde ana sahneyi tanımlayan anahtar.
_MAIN_SCENE = re.compile(r"^\s*run/main_scene\s*=\s*\S")
_SECTION = re.compile(r"^\s*\[")

#: Godot'un içe aktarma gerektiren görsel/ses uzantıları.
_GODOT_IMPORTED_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".ogg", ".wav", ".mp3"})


def godot_has_main_scene(root: Path) -> bool:
    """Godot projesi çalıştırılabilir mi: ana sahne tanımlı ve diskte mi.

    Bölümsüz yazılmış anahtar SAYILMAZ; Godot da saymaz ve "no main scene
    defined in the project" der (bkz. `core/structured_files.py`).
    """
    try:
        content = (root / "project.godot").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    in_section = False
    for line in content.splitlines():
        if _SECTION.match(line):
            in_section = True
        elif in_section and _MAIN_SCENE.match(line):
            # Tanımlı olması yetmez: dosya DİSKTE de olmalı.
            #
            # Ölçüldü (13 Eylül, koşu 32): `run/main_scene="res://scenes/main.tscn"`
            # yazıyordu ama dosya hiç yazılmamıştı. Proje "çalıştırılabilir" sayıldı,
            # kurulum kapısı (içe aktarma) atlandı ve çalıştırma kapısı üç satır
            # ERROR'a rağmen sıfır çıkışla geçti.
            return _declared_main_scene_exists(root, line)
    return False


def _declared_main_scene_exists(root: Path, line: str) -> bool:
    """`run/main_scene` satırındaki sahne dosyası diskte var mı?"""
    eslesme = re.search(r'res://(?P<yol>[^"\']+)', line)
    if eslesme is None:
        return False
    return (root / eslesme.group("yol").strip()).is_file()


def godot_needs_import(root: Path) -> bool:
    """Projede İÇE AKTARILMAMIŞ varlık var mı?

    Godot bir PNG'yi ancak içe aktardıktan sonra yükleyebilir; yanında bir
    `<dosya>.import` üretir. Editör hiç açılmadan eklenen dosyalar için bu kayıt
    yoktur ve `load("res://...png")` çalışma anında düşer.

    Ölçüldü (13 Eylül, Godot koşusu): 400 karo indirilip açıldı, kod doğru yolu
    yüklüyordu ve motor `No loader found for resource:
    res://assets/Tiles/Default/tile_0000.png` bastı — üstelik çıkış kodu 0'dı.
    """
    for path in root.rglob("*"):
        if path.suffix.casefold() not in _GODOT_IMPORTED_SUFFIXES:
            continue
        if any(part in SKIP_DIRECTORIES or part.startswith(".") for part in path.parts):
            continue
        if not path.with_suffix(path.suffix + ".import").exists():
            return True
    return False


def _godot_preparation(root: Path) -> tuple[str, ...]:
    """İçe aktarılmamış varlık varsa kapıdan önce bir kez içe aktar."""
    if not godot_needs_import(root):
        return ()
    return ("godot --headless --path . --editor --quit",)


def godot_adapter() -> DomainAdapter:
    """Godot kanıt sözleşmesi.

    Kapı `--headless --quit` ile projenin AÇILDIĞINI ölçer. Ölçülen hata: model bozuk
    `project.godot` ve `main.tscn` üretti, tur "tamamlandı" dedi; Godot elle
    çalıştırıldığında iki saniyede `no main scene defined in the project` diyordu.
    """
    return DomainAdapter(
        name="godot",
        marker="project.godot",
        gates=("godot --headless --path . --quit",),
        setup_gates=("godot --headless --path . --editor --quit",),
        is_runnable=godot_has_main_scene,
        preparation=_godot_preparation,
        executable="godot",
        # "no loader found" sıfır çıkışla basılır ve oyunun varlığı yükleyemediğini
        # söyler; kapının sessiz kalması tam da bu yüzden yanlıştır.
        output_failure_markers=(
            "script error",
            "parse error",
            "can't run project",
            "failed to load script",
            "no loader found",
            # Ölçüldü (koşu 32): ana sahne dosyası yoktu; motor "Cannot open file"
            # ve "Failed loading scene" bastı, çıkış kodu yine 0'dı.
            "cannot open file",
            "failed loading",
        ),
        criteria=(
            "project.godot içinde ana sahne (run/main_scene) tanımlı",
            "godot --headless çalıştığında hiçbir SCRIPT ERROR / Parse Error basılmıyor",
            "sahnedeki düğüm tipi, bağlı script'in kullandığı API ile uyumlu",
        ),
        # Yalnız Godot'u ADIYLA anan kelimeler: "oyun"/"game" tarayıcı oyununa da
        # Godot koşulu sokardı.
        task_markers=("godot", "gdscript", "tscn"),
    )
```

- [ ] **Adım 4: Web adaptörü, varsayılan kayıt ve uyum modülünü yaz**

`src/fusion_cli/engines/agent/domain_adapters/web.py`:
```python
"""Web alanı — sayfa gerçekten yükleniyor ve konsolda hata yok.

İşaret kökteki `index.html`'dir. `package.json` tek başına web kanıtı DEĞİLDİR:
CLI araçları, kütüphaneler ve sunucular da onu taşır.
"""

from __future__ import annotations

from .contract import DomainAdapter


def web_adapter() -> DomainAdapter:
    """Web kanıt sözleşmesi."""
    return DomainAdapter(
        name="web",
        marker="index.html",
        criteria=(
            "sayfa tarayıcıda hatasız yükleniyor",
            "konsolda hata yok",
            "kritik kullanıcı akışı tıklanabiliyor",
        ),
        task_markers=("html", "web sayfası", "web sitesi", "website", "landing page"),
    )
```

`src/fusion_cli/engines/agent/domain_adapters/defaults.py`:
```python
"""Fusion'ın varsayılan alan kaydını kuran fabrika.

Modül seviyesinde kayıt TUTULMAZ; her çağrı yeni (ama eşit) bir değer üretir. Yeni
alan eklemek aşağıdaki demete bir adaptör eklemektir; motor dosyası değişmez.
"""

from __future__ import annotations

from .godot import godot_adapter
from .registry import DomainRegistry
from .web import web_adapter


def default_domain_registry() -> DomainRegistry:
    """Kayıtlı alanlar, eşleşme ve kapı sırasıyla."""
    return DomainRegistry((godot_adapter(), web_adapter()))
```

`src/fusion_cli/engines/agent/domains.py` — dosyanın TAMAMI şununla değiştirilir:
```python
"""Alan adaptörleri için geriye uyumlu giriş noktası.

Sözleşme, kayıt defteri ve alan paketleri `domain_adapters` paketindedir. Bu modül
yalnız mevcut içe aktarmaların (`domains.godot_adapter` vb.) çalışmaya devam etmesi
için adları yeniden dışa açar; yeni kod doğrudan `domain_adapters` paketini kullanır.
"""

from __future__ import annotations

from pathlib import Path

from .domain_adapters.contract import DomainAdapter
from .domain_adapters.defaults import default_domain_registry
from .domain_adapters.godot import godot_adapter, godot_has_main_scene, godot_needs_import
from .domain_adapters.web import web_adapter

__all__ = [
    "DomainAdapter",
    "adapter_for",
    "godot_adapter",
    "godot_has_main_scene",
    "godot_needs_import",
    "web_adapter",
]


def adapter_for(root: Path) -> DomainAdapter | None:
    """Bu proje varsayılan kayıttaki bir alana ait mi? Değilse `None`."""
    return default_domain_registry().first_match(root)
```

- [ ] **Adım 5: Yeni ve eski alan testlerinin geçtiğini gör**

Run: `.venv/bin/pytest tests/test_domain_defaults.py tests/test_domains.py tests/test_domain_adapters.py tests/test_godot_setup_gate.py tests/test_verify_discovery.py tests/test_verification_gate.py -q`
Expected: hepsi PASS (eski dosyalar dokunulmadan).

- [ ] **Adım 6: Kalite kapısı**

Run: `.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest -q`
Expected: üçü temiz.

- [ ] **Adım 7: Commit**

```bash
git add src/fusion_cli/engines/agent/domain_adapters/godot.py \
  src/fusion_cli/engines/agent/domain_adapters/web.py \
  src/fusion_cli/engines/agent/domain_adapters/defaults.py \
  src/fusion_cli/engines/agent/domains.py \
  tests/test_domain_defaults.py
git commit -m "refactor(alan): godot ve web adaptörlerini alan paketine taşı"
```

---

### Görev 3: Keşif ve sıfır-çıkış işaretlerini alan kaydından al

**Dosyalar:**
- Modify: `src/fusion_cli/engines/agent/verify_discovery.py` (import bloğu, `discover_auto_commands`,
  `discover_commands`, `behavioral_commands`; `_godot` silinir)
- Modify: `src/fusion_cli/engines/agent/verification.py` (import bloğu, `build_verifier`,
  `CommandVerifier.__init__`, `CommandVerifier._run` içindeki `_reported_failure` çağrısı,
  `_ZERO_EXIT_FAILURE_MARKERS` silinir, `_reported_failure`)
- Test: `tests/test_domain_wiring.py`

**Arayüzler:**
- Tüketir: `DomainRegistry.gate_commands`, `DomainRegistry.output_failure_markers`,
  `default_domain_registry()`, `ToolFailureMarkers`.
- Üretir:
  - `discover_commands(root, *, node_scripts=..., include_tests=True, domains: DomainRegistry | None = None)`
  - `discover_auto_commands(root, *, domains: DomainRegistry | None = None)`
  - `behavioral_commands(root, *, domains: DomainRegistry | None = None)`
  - `build_verifier(config, *, root, tool_context, domains: DomainRegistry | None = None)`
  - `CommandVerifier(commands, *, cwd, timeout_s, failure_markers: tuple[ToolFailureMarkers, ...] | None = None)`

- [ ] **Adım 1: Başarısız testi yaz**

`tests/test_domain_wiring.py`:
```python
"""Keşif ve komut kapısı alan bilgisini motordan değil kayıt defterinden alır.

Kanıt iki yönlüdür: sahte bir alan motora dokunmadan kapısını getirir; boş kayıt
defteriyle Godot projesinde hiçbir Godot komutu üretilmez (bilgi gömülü değildir).
"""

from __future__ import annotations

import json

from fusion_cli.engines.agent.domain_adapters.contract import DomainAdapter, ToolFailureMarkers
from fusion_cli.engines.agent.domain_adapters.registry import DomainRegistry
from fusion_cli.engines.agent.verification import CommandVerifier, build_verifier
from fusion_cli.engines.agent.verify_discovery import discover_auto_commands, discover_commands

from .fakes import make_config

_SAHTE = DomainAdapter(name="sahte", marker="sahte.proj", gates=("sahte-kapi --kontrol",))


def _kayit(*adaptorler: DomainAdapter) -> DomainRegistry:
    return DomainRegistry(adaptorler)


def test_alan_kapisi_kayit_defterinden_gelir(tmp_path):
    (tmp_path / "sahte.proj").write_text("", encoding="utf-8")

    assert discover_commands(tmp_path, domains=_kayit(_SAHTE)) == ("sahte-kapi --kontrol",)


def test_python_kesfi_alan_kapisindan_once_gelir(tmp_path):
    (tmp_path / "sahte.proj").write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")

    assert discover_commands(tmp_path, domains=_kayit(_SAHTE)) == ("ruff check .",)


def test_node_kesfi_alan_kapisindan_once_gelir(tmp_path):
    (tmp_path / "sahte.proj").write_text("", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"typecheck": "tsc --noEmit"}}), encoding="utf-8"
    )

    assert discover_auto_commands(tmp_path, domains=_kayit(_SAHTE)) == ("npm run typecheck",)


def test_alan_kapisi_rust_kesfinden_once_gelir(tmp_path):
    (tmp_path / "sahte.proj").write_text("", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")

    assert discover_commands(tmp_path, domains=_kayit(_SAHTE)) == ("sahte-kapi --kontrol",)


def test_bos_kayit_defteriyle_godot_projesinde_godot_komutu_uretilmez(tmp_path):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")

    assert discover_commands(tmp_path, domains=_kayit()) == ()


async def test_komut_kapisi_enjekte_edilen_isaretleri_kullanir(tmp_path):
    komut = "sahte() { echo 'KRITIK HATA: sahne bozuk'; }; sahte --kontrol"

    isaretli = CommandVerifier(
        (komut,),
        cwd=str(tmp_path),
        timeout_s=5,
        failure_markers=(ToolFailureMarkers("sahte", ("kritik hata",)),),
    )
    isaretsiz = CommandVerifier((komut,), cwd=str(tmp_path), timeout_s=5, failure_markers=())

    assert (await isaretli.verify()).ok is False
    assert (await isaretsiz.verify()).ok is True


async def test_dogrulayici_kurucusu_kayit_defterinin_kapi_ve_isaretlerini_kullanir(tmp_path):
    (tmp_path / "sahte.proj").write_text("", encoding="utf-8")
    adaptor = DomainAdapter(
        name="sahte",
        marker="sahte.proj",
        gates=("sahte() { echo 'KRITIK HATA'; }; sahte --kontrol",),
        executable="sahte",
        output_failure_markers=("kritik hata",),
    )
    config = make_config(runtime={"web_verification": False, "browser_verification": False})

    verifier = build_verifier(config, root=tmp_path, tool_context=None, domains=_kayit(adaptor))

    assert verifier is not None
    sonuc = await verifier.verify()
    assert sonuc.ok is False
    assert "kritik hata" in sonuc.summary
```

- [ ] **Adım 2: Testin düştüğünü gör**

Run: `.venv/bin/pytest tests/test_domain_wiring.py -q`
Expected: FAIL — `TypeError: discover_commands() got an unexpected keyword argument 'domains'` (ve
`failure_markers` için benzeri).

- [ ] **Adım 3: Keşfi kayıt defterine bağla**

`src/fusion_cli/engines/agent/verify_discovery.py` import bloğunda:

Eski:
```python
import json
import re
from pathlib import Path

from .domains import godot_adapter
```
Yeni:
```python
import json
import re
from collections.abc import Callable
from functools import partial
from pathlib import Path

from .domain_adapters.defaults import default_domain_registry
from .domain_adapters.registry import DomainRegistry
```

`discover_auto_commands` gövdesinin tamamı:

Eski:
```python
def discover_auto_commands(root: Path) -> tuple[str, ...]:
```
Yeni imza (docstring aynen kalır):
```python
def discover_auto_commands(
    root: Path, *, domains: DomainRegistry | None = None
) -> tuple[str, ...]:
```
ve son satırı:

Eski:
```python
    return discover_commands(root, node_scripts=_AUTO_NODE_SCRIPTS, include_tests=False)
```
Yeni:
```python
    return discover_commands(
        root, node_scripts=_AUTO_NODE_SCRIPTS, include_tests=False, domains=domains
    )
```

`discover_commands` fonksiyonunun TAMAMI:

Eski:
```python
def discover_commands(
    root: Path,
    *,
    node_scripts: tuple[str, ...] = _NODE_SCRIPTS,
    include_tests: bool = True,
) -> tuple[str, ...]:
    """Proje kökünden doğrulama planı çıkar. Bulunamazsa boş demet.

    Sıra MALİYETE göredir: lint → tip denetimi → test. Kapı ilk başarısız komutta
    durur; pahalı olan öne alınsaydı her kırık turda boşuna beklenirdi.
    """
    for kesif in (_python, _node, _godot, _rust, _go, _make):
        plan = kesif(root) if kesif is not _node else _node(root, node_scripts)
        if plan:
            return (
                plan
                if include_tests
                else tuple(komut for komut in plan if not _is_test_command(komut))
            )
    return ()
```
Yeni:
```python
def discover_commands(
    root: Path,
    *,
    node_scripts: tuple[str, ...] = _NODE_SCRIPTS,
    include_tests: bool = True,
    domains: DomainRegistry | None = None,
) -> tuple[str, ...]:
    """Proje kökünden doğrulama planı çıkar. Bulunamazsa boş demet.

    Sıra MALİYETE göredir: lint → tip denetimi → test. Kapı ilk başarısız komutta
    durur; pahalı olan öne alınsaydı her kırık turda boşuna beklenirdi.

    Alan kapıları (Godot vb.) kayıt defterinden gelir ve Node ile Rust arasındaki
    yerini korur; ilk boş olmayan keşif kazanır. `domains` verilmezse varsayılan
    kayıt o anda kurulur.
    """
    registry = domains if domains is not None else default_domain_registry()
    kesifler: tuple[Callable[[Path], tuple[str, ...]], ...] = (
        _python,
        partial(_node, scripts=node_scripts),
        registry.gate_commands,
        _rust,
        _go,
        _make,
    )
    for kesif in kesifler:
        plan = kesif(root)
        if plan:
            return (
                plan
                if include_tests
                else tuple(komut for komut in plan if not _is_test_command(komut))
            )
    return ()
```

`behavioral_commands` imzası ve dönüşü:

Eski:
```python
def behavioral_commands(root: Path) -> tuple[str, ...]:
```
Yeni:
```python
def behavioral_commands(root: Path, *, domains: DomainRegistry | None = None) -> tuple[str, ...]:
```
Eski:
```python
        for command in discover_commands(root)
```
Yeni:
```python
        for command in discover_commands(root, domains=domains)
```

`_godot` fonksiyonunu (docstring'i dahil, `def _godot(root: Path) -> tuple[str, ...]:` satırından
`return adaptor.gate_commands(root) if adaptor.matches(root) else ()` satırına kadar) SİL. Docstring'deki
ölçüm notu zaten `godot_adapter()` docstring'ine taşındı (Görev 2).

- [ ] **Adım 4: Komut doğrulayıcıyı kayıt defterine bağla**

`src/fusion_cli/engines/agent/verification.py` import bloğunda:

Eski:
```python
from .browser_verify import BrowserVerifier
from .domains import godot_adapter
from .javascript_verify import (
```
Yeni:
```python
from .browser_verify import BrowserVerifier
from .domain_adapters.contract import ToolFailureMarkers
from .domain_adapters.defaults import default_domain_registry
from .domain_adapters.registry import DomainRegistry
from .javascript_verify import (
```

`build_verifier` imzası:

Eski:
```python
def build_verifier(
    config: Config, *, root: Path, tool_context: ToolContext | None
) -> Verifier | None:
```
Yeni:
```python
def build_verifier(
    config: Config,
    *,
    root: Path,
    tool_context: ToolContext | None,
    domains: DomainRegistry | None = None,
) -> Verifier | None:
```
Docstring'in son paragrafından sonra (kapanış `"""` öncesi) şu paragrafı ekle:
```text
    `domains` alan kaydıdır: keşfedilen alan kapıları ve sıfır-çıkış işaretleri
    buradan gelir. Verilmezse varsayılan kayıt kurulur; kayıt değer nesnesi olduğu
    için `AgentDeps.domains` ile ayrışmaz.
```
Gövdede:

Eski:
```python
    verifiers: list[Verifier] = []
```
Yeni:
```python
    verifiers: list[Verifier] = []
    registry = domains if domains is not None else default_domain_registry()
```
Eski:
```python
    commands = config.runtime.verification_commands or discover_auto_commands(root)
    if commands:
        verifiers.append(CommandVerifier(commands, cwd=str(root), timeout_s=SHELL_TIMEOUT_S))
```
Yeni:
```python
    commands = config.runtime.verification_commands or discover_auto_commands(
        root, domains=registry
    )
    if commands:
        verifiers.append(
            CommandVerifier(
                commands,
                cwd=str(root),
                timeout_s=SHELL_TIMEOUT_S,
                failure_markers=registry.output_failure_markers(),
            )
        )
```

`CommandVerifier.__init__`:

Eski:
```python
    def __init__(self, commands: tuple[str, ...], *, cwd: str, timeout_s: float) -> None:
        self._commands = commands
        self._cwd = cwd
        self._timeout_s = timeout_s
```
Yeni:
```python
    def __init__(
        self,
        commands: tuple[str, ...],
        *,
        cwd: str,
        timeout_s: float,
        failure_markers: tuple[ToolFailureMarkers, ...] | None = None,
    ) -> None:
        self._commands = commands
        self._cwd = cwd
        self._timeout_s = timeout_s
        # İşaretler alan kaydından gelir; verilmezse varsayılan kaydın işaretleri.
        # Tarama proje işaretinden bağımsızdır: hatayı basıp `0` dönen ARAÇTIR.
        self._failure_markers = (
            failure_markers
            if failure_markers is not None
            else default_domain_registry().output_failure_markers()
        )
```

`_run` içinde:

Eski:
```python
            bildirilen = _reported_failure(command, output)
```
Yeni:
```python
            bildirilen = _reported_failure(command, output, self._failure_markers)
```

Dosya sonundaki global tabloyu ve fonksiyonu değiştir:

Eski:
```python
#: Sıfır çıkış koduna rağmen hatayı yalnız ÇIKTIYA basan araçlar.
#
# Ölçüldü: Godot hem bozuk script'te hem çalışma zamanı hatasında `0` döndürüyor;
# çıkış koduna bakan kapı bunu "başarıyla çalıştı" sayıp kabul veriyordu. Tablo
# araç adına göre genişletilir. İşaretler dar tutulur: yalnız motorun KENDİ hata
# satırında geçen ifadeler yazılır, yoksa kapı gürültüye döner.
_ZERO_EXIT_FAILURE_MARKERS: dict[str, tuple[str, ...]] = {
    # İşaretler alan adaptöründen gelir: aynı bilgi iki yerde durursa zamanla
    # ayrışır ve biri güncellenirken öteki sessizce eskir.
    godot_adapter().name: godot_adapter().zero_exit_failure_markers(),
}


def _reported_failure(command: str, output: str) -> str:
    """Çıkış kodu sessiz kalsa da aracın kendi bildirdiği hatayı yakala."""
    lowered = output.casefold()
    for tool, markers in _ZERO_EXIT_FAILURE_MARKERS.items():
        if not re.search(rf"\b{re.escape(tool)}\b", command):
            continue
        for marker in markers:
            if marker in lowered:
                return marker
    return ""
```
Yeni:
```python
def _reported_failure(
    command: str, output: str, failure_markers: tuple[ToolFailureMarkers, ...]
) -> str:
    """Çıkış kodu sessiz kalsa da aracın kendi bildirdiği hatayı yakala.

    Ölçüldü: motor hem bozuk script'te hem çalışma zamanı hatasında `0` döndürüyor;
    çıkış koduna bakan kapı bunu "başarıyla çalıştı" sayıp kabul veriyordu. İşaretler
    alan kaydından gelir ve dar tutulur: yalnız aracın KENDİ hata satırında geçen
    ifadeler, yoksa kapı gürültüye döner.
    """
    lowered = output.casefold()
    for entry in failure_markers:
        if not re.search(rf"\b{re.escape(entry.tool)}\b", command):
            continue
        for marker in entry.markers:
            if marker in lowered:
                return marker
    return ""
```

- [ ] **Adım 5: Testlerin geçtiğini gör**

Run: `.venv/bin/pytest tests/test_domain_wiring.py tests/test_verify_discovery.py tests/test_verification_gate.py tests/test_godot_setup_gate.py tests/test_step_verification.py tests/test_classify_verify.py tests/test_javascript_verify.py tests/test_eval_agent_runner.py -q`
Expected: hepsi PASS. `test_sifir_cikis_kodu_motorun_hata_bildirimini_gizlemez` (project.godot YOK) hâlâ
geçmeli — işaret taramasının proje işaretinden bağımsızlığının kanıtı.

- [ ] **Adım 6: Kalite kapısı**

Run: `.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest -q`
Expected: üçü temiz. `mypy` `partial` için hata verirse `partial(_node, scripts=node_scripts)` yerine
şu yerel fonksiyonu kullan (davranış aynı):
```python
    def _node_kesfi(kok: Path) -> tuple[str, ...]:
        return _node(kok, node_scripts)
```
ve demette `_node_kesfi` yaz; `from functools import partial` importunu kaldır.

- [ ] **Adım 7: Commit**

```bash
git add src/fusion_cli/engines/agent/verify_discovery.py \
  src/fusion_cli/engines/agent/verification.py \
  tests/test_domain_wiring.py
git commit -m "refactor(dogrulama): keşif kapılarını ve sıfır çıkış işaretlerini alan kaydından al"
```

---

### Görev 4: Final kabuldeki çapraz dosya denetimlerini alan kaydına bağla

**Dosyalar:**
- Modify: `src/fusion_cli/engines/agent/loop.py` (`AgentDeps` alanı + import)
- Modify: `src/fusion_cli/engines/agent/step_verification.py` (`core.cross_file` importu silinir,
  `verify_plan_acceptance` çapraz denetim bloğu, `behavioral_commands` çağrısı)
- Modify: `src/fusion_cli/engines/agent/domain_adapters/godot.py` (`artifact_suffixes`, `artifact_checks`)
- Modify: `tests/test_plan_runner.py` (`_FakeDeps`), `tests/test_plan_resume.py` (`_Deps`)
- Test: `tests/test_domain_acceptance.py`

**Arayüzler:**
- Tüketir: `DomainRegistry.artifact_findings(root)`, `default_domain_registry()`,
  `behavioral_commands(root, *, domains)` (Görev 3).
- Üretir: `AgentDeps.domains: DomainRegistry` (varsayılan `default_domain_registry()`); Godot adaptörü
  `artifact_suffixes=(".gd", ".tscn", ".tres")` ve altı çapraz denetimi bugünkü sırayla taşır.

- [ ] **Adım 1: Başarısız testi yaz**

`tests/test_domain_acceptance.py`:
```python
"""Final kabulün çapraz/artifact denetimleri alan kaydından gelir.

Motor hangi alanın hangi sessiz hatayı ürettiğini bilmez. Varsayılan kayıtla Godot
çatışması `project.godot` yokken de yakalanmaya devam eder (davranış korunur); boş
kayıtla motor hiçbir Godot denetimi çalıştırmaz (bilgi gömülü değildir).
"""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.core.execution_plan import ExecutionPlan, PlanStep, RetrySafety, StepStatus
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.domain_adapters.contract import DomainAdapter
from fusion_cli.engines.agent.domain_adapters.registry import DomainRegistry
from fusion_cli.engines.agent.loop import AgentDeps
from fusion_cli.engines.agent.step_verification import verify_plan_acceptance

from .fakes import AlwaysApprove, make_config

SAHNE = (
    "[gd_scene load_steps=2 format=3]\n\n"
    '[ext_resource type="Script" path="res://player.gd" id="1_player"]\n\n'
    '[node name="Main" type="Node2D"]\n\n'
    '[node name="Player" type="Area2D" parent="."]\n'
    'script = ExtResource("1_player")\n'
)
SCRIPT = (
    "extends CharacterBody2D\n\n"
    "func _physics_process(delta):\n"
    "\tvelocity = Vector2.ZERO\n"
    "\tmove_and_slide()\n"
)


class _Publisher:
    def publish(self, event):
        del event


def _deps(tmp_path, domains: DomainRegistry | None = None) -> AgentDeps:
    deps = AgentDeps(
        config=make_config(),
        publisher=_Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )
    if domains is not None:
        deps.domains = domains
    return deps


def _plan(path: str) -> ExecutionPlan:
    step = PlanStep(
        step_id="create",
        goal="dosyayı oluştur",
        depends_on=(),
        expected_effects=(f"file:{path}",),
        allowed_tool_families=("files",),
        success_criteria=("dosya bulunuyor",),
        verification_hint="dosyayı oku",
        retry_safety=RetrySafety.SAFE,
    )
    return ExecutionPlan("p", "iş", (replace(step, status=StepStatus.COMPLETED),))


def _godot_catismasi(tmp_path) -> None:
    (tmp_path / "main.tscn").write_text(SAHNE, encoding="utf-8")
    (tmp_path / "player.gd").write_text(SCRIPT, encoding="utf-8")


async def test_final_kabul_alanin_artifact_bulgusunu_engelleyici_sayar(tmp_path):
    (tmp_path / "medya.json").write_text("{}", encoding="utf-8")
    adaptor = DomainAdapter(
        name="medya",
        marker="medya.json",
        artifact_checks=(lambda kok: ("cikti/video.mp4 üretilmedi",),),
    )

    sonuc = await verify_plan_acceptance(
        _plan("medya.json"), _deps(tmp_path, DomainRegistry((adaptor,)))
    )

    assert sonuc.ok is False
    assert sonuc.findings == ("cikti/video.mp4 üretilmedi",)


async def test_bos_kayitla_motor_godot_capraz_denetimi_calistirmaz(tmp_path):
    _godot_catismasi(tmp_path)

    sonuc = await verify_plan_acceptance(_plan("main.tscn"), _deps(tmp_path, DomainRegistry(())))

    assert sonuc.ok is True


async def test_varsayilan_kayit_project_godot_yokken_de_sahne_catismasini_yakalar(tmp_path):
    """Korunan davranış: çapraz denetim bugün `project.godot` şartı olmadan çalışıyor."""
    _godot_catismasi(tmp_path)

    sonuc = await verify_plan_acceptance(_plan("main.tscn"), _deps(tmp_path))

    assert sonuc.ok is False
    assert "Area2D" in sonuc.summary
```

- [ ] **Adım 2: Testin düştüğünü gör**

Run: `.venv/bin/pytest tests/test_domain_acceptance.py -q`
Expected: ilk iki test FAIL (`AgentDeps` üzerinde `domains` alanı yok → `AttributeError` slots nedeniyle;
boş kayıt testi Godot çatışmasıyla düşer); üçüncü test PASS (korunan davranışın bekçisi).

- [ ] **Adım 3: `AgentDeps.domains` alanını ekle**

`src/fusion_cli/engines/agent/loop.py` import bloğunda:

Eski:
```python
from .classify import TaskClassification, TaskKind, classify_task_details, recall_scope, scope_of
```
Yeni:
```python
from .classify import TaskClassification, TaskKind, classify_task_details, recall_scope, scope_of
from .domain_adapters.defaults import default_domain_registry
from .domain_adapters.registry import DomainRegistry
```

`AgentDeps` içinde:

Eski:
```python
    verifier: Verifier | None = None
    #: Oturum boyunca paylaşılan sağlayıcı sağlığı (circuit breaker + güvenilirlik).
```
Yeni:
```python
    verifier: Verifier | None = None
    #: Alan kaydı: kapılar, sıfır-çıkış işaretleri, artifact denetimleri, kabul
    #: koşulları ve alan teslimatları buradan gelir. Motor hiçbir alanın adını bilmez;
    #: yeni alan eklemek bu kayda adaptör eklemektir.
    domains: DomainRegistry = field(default_factory=default_domain_registry)
    #: Oturum boyunca paylaşılan sağlayıcı sağlığı (circuit breaker + güvenilirlik).
```

- [ ] **Adım 4: Final kabulü kayda bağla**

`src/fusion_cli/engines/agent/step_verification.py` import bloğundan şu bloğu SİL:
```python
from ...core.cross_file import (
    broken_resource_paths,
    missing_node_references,
    promised_key_conflicts,
    runtime_script_conflicts,
    scene_script_conflicts,
    scripts_without_base,
)
```

`verify_plan_acceptance` içinde:

Eski:
```python
    # Tek dosya doğru, bütün bozuk olabilir: ölçüldü (Godot koşusu), sahnedeki düğüm
    # tipi ile script'in beklediği taban uyuşmuyordu ve motor sıfır çıkış koduyla
    # parse hatası bastı. Bu sınıf hatayı ne dil kapısı ne de çalıştırma kapısı
    # yakalar; çapraz denetim motor çalışmadan önce söyler.
    # Üç çapraz denetim de SESSİZ hata sınıfını hedefler: motor sıfır çıkışla
    # açılır, kapı geçer, kullanıcı oyunu açar ve hiçbir şey çalışmaz.
    catismalar = (
        scene_script_conflicts(deps.tool_context.root)
        + runtime_script_conflicts(deps.tool_context.root)
        + promised_key_conflicts(deps.tool_context.root)
        + missing_node_references(deps.tool_context.root)
        + broken_resource_paths(deps.tool_context.root)
        + scripts_without_base(deps.tool_context.root)
    )
    if catismalar:
```
Yeni:
```python
    # Tek dosya doğru, bütün bozuk olabilir: bu sınıf hatayı ne dil kapısı ne de
    # çalıştırma kapısı yakalar (araç sıfır çıkışla açılır, kapı geçer, teslim
    # çalışmaz). Alanın artifact denetimleri bunu motor koşmadan söyler; hangi
    # denetimin çalışacağını motor değil alan kaydı bilir.
    catismalar = deps.domains.artifact_findings(deps.tool_context.root)
    if catismalar:
```

Aynı fonksiyonun sonunda:

Eski:
```python
    expected_behavior = set(behavioral_commands(deps.tool_context.root))
```
Yeni:
```python
    expected_behavior = set(behavioral_commands(deps.tool_context.root, domains=deps.domains))
```

- [ ] **Adım 5: Godot adaptörüne çapraz denetimleri ver**

`src/fusion_cli/engines/agent/domain_adapters/godot.py` import bloğunda:

Eski:
```python
from ....core.constants import SKIP_DIRECTORIES
from .contract import DomainAdapter
```
Yeni:
```python
from ....core.constants import SKIP_DIRECTORIES
from ....core.cross_file import (
    broken_resource_paths,
    missing_node_references,
    promised_key_conflicts,
    runtime_script_conflicts,
    scene_script_conflicts,
    scripts_without_base,
)
from .contract import DomainAdapter
```

`godot_adapter()` içinde:

Eski:
```python
        task_markers=("godot", "gdscript", "tscn"),
    )
```
Yeni:
```python
        task_markers=("godot", "gdscript", "tscn"),
        # Denetimlerin baktığı dosya kümesi: `project.godot` henüz yazılmamışken de
        # sahne/script ağaçta durabilir ve çatışma o anda da gerçektir.
        artifact_suffixes=(".gd", ".tscn", ".tres"),
        # Sıra bugünkü final kabul sırasıdır; ilk bulgu özet olur.
        # Hepsi SESSİZ hata sınıfını hedefler (ölçüldü, 6-13 Eylül koşuları): motor
        # sıfır çıkışla açılır, kapı geçer, kullanıcı oyunu açar ve hiçbir şey çalışmaz.
        artifact_checks=(
            scene_script_conflicts,
            runtime_script_conflicts,
            promised_key_conflicts,
            missing_node_references,
            broken_resource_paths,
            scripts_without_base,
        ),
    )
```

- [ ] **Adım 6: Sahte bağımlılıklara alan kaydını ekle**

`tests/test_plan_runner.py`, import bloğuna (`from fusion_cli.engines.agent.loop import AgentOutcome`
satırının üstüne):
```python
from fusion_cli.engines.agent.domain_adapters.defaults import default_domain_registry
from fusion_cli.engines.agent.domain_adapters.registry import DomainRegistry
```
`_FakeDeps` içinde:

Eski:
```python
    config: object | None = None
    publisher: object = field(default_factory=_Publisher)
```
Yeni:
```python
    config: object | None = None
    publisher: object = field(default_factory=_Publisher)
    domains: DomainRegistry = field(default_factory=default_domain_registry)
```

`tests/test_plan_resume.py`:

Eski:
```python
from dataclasses import dataclass
```
Yeni:
```python
from dataclasses import dataclass, field
```
Eski:
```python
from fusion_cli.engines.agent.loop import AgentOutcome
```
Yeni:
```python
from fusion_cli.engines.agent.domain_adapters.defaults import default_domain_registry
from fusion_cli.engines.agent.domain_adapters.registry import DomainRegistry
from fusion_cli.engines.agent.loop import AgentOutcome
```
`_Deps` içinde:

Eski:
```python
    publisher: object = _Publisher()
```
Yeni:
```python
    publisher: object = _Publisher()
    domains: DomainRegistry = field(default_factory=default_domain_registry)
```

- [ ] **Adım 7: Testlerin geçtiğini gör**

Run: `.venv/bin/pytest tests/test_domain_acceptance.py tests/test_step_verification.py tests/test_godot_silent_failures.py tests/test_cross_file_consistency.py tests/test_plan_runner.py tests/test_plan_resume.py tests/test_plan_repair.py tests/test_plan_quality.py tests/test_attempts_wiring.py tests/test_plan_parser_tolerance.py -q`
Expected: hepsi PASS. Başka bir sahte bağımlılık `AttributeError: ... 'domains'` verirse, o sahte
dataclass'a Adım 6'daki alanı (ve iki importu) aynı biçimde ekle; `SimpleNamespace` ise
`domains=default_domain_registry()` argümanını ekle. Test mantığını değiştirme.

- [ ] **Adım 8: Kalite kapısı**

Run: `.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest -q`
Expected: üçü temiz.

- [ ] **Adım 9: Commit**

```bash
git add src/fusion_cli/engines/agent/loop.py \
  src/fusion_cli/engines/agent/step_verification.py \
  src/fusion_cli/engines/agent/domain_adapters/godot.py \
  tests/test_plan_runner.py tests/test_plan_resume.py tests/test_domain_acceptance.py
git commit -m "refactor(kabul): çapraz dosya denetimlerini alan kaydına bağla"
```
(Adım 7'de başka test dosyası düzeltildiyse onu da adıyla ekle.)

---

### Görev 5: Alan kabul koşullarını plana ver, oyun teslimatlarını Godot alanına taşı

**Dosyalar:**
- Create: `src/fusion_cli/engines/agent/prompts/domain_acceptance.md`
- Modify: `src/fusion_cli/engines/agent/plan_generation.py` (import, `_planning_prompt` eklenir,
  `generate_plan` başı ve kapsama çağrısı)
- Modify: `src/fusion_cli/engines/agent/plan_coverage.py` (`DELIVERABLES`, `missing_deliverables`)
- Modify: `src/fusion_cli/engines/agent/domain_adapters/godot.py` (iki teslimat + `deliverables`)
- Modify: `tests/test_plan_coverage.py`
- Test: `tests/test_domain_planning.py`

**Arayüzler:**
- Tüketir: `AgentDeps.domains` (Görev 4), `DomainRegistry.acceptance_criteria(root, task)`,
  `DomainRegistry.deliverables()`.
- Üretir: `missing_deliverables(task, plan, *, domain_deliverables: tuple[Deliverable, ...]) -> tuple[Deliverable, ...]`
  (anahtar ZORUNLU); `plan_coverage.DELIVERABLES` yalnız asset ve UI.

- [ ] **Adım 1: Başarısız testi yaz**

`tests/test_domain_planning.py`:
```python
"""Planlayıcı alanın kabul koşullarını görür; oyun teslimatları Godot alanına aittir.

`acceptance_criteria` bugüne dek hiçbir istemde yoktu: plan, işin alanda neyle
BİTTİĞİNİ bilmeden kuruluyordu. Koşullar kök işaretinden ya da görevde alanın adıyla
anılmasından gelir; "oyun" kelimesi tek başına Godot koşulu getirmez.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from fusion_cli.core.execution_plan import ExecutionPlan, PlanStep, RetrySafety
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.domain_adapters.contract import DomainAdapter
from fusion_cli.engines.agent.domain_adapters.defaults import default_domain_registry
from fusion_cli.engines.agent.domain_adapters.registry import DomainRegistry
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.plan_coverage import missing_deliverables
from fusion_cli.engines.agent.plan_generation import generate_plan

_BASLIK = "ALAN KABUL KOŞULLARI"
_PLAN = json.dumps(
    {
        "plan_id": "p1",
        "task": "iş",
        "steps": [
            {
                "step_id": "s1",
                "goal": "işi yap",
                "depends_on": [],
                "expected_effects": ["file:a.txt"],
                "allowed_tool_families": ["files"],
                "success_criteria": ["dosya yazıldı"],
                "verification_hint": "",
                "retry_safety": "safe",
            }
        ],
    },
    ensure_ascii=False,
)


class _IstemKaydedici:
    def __init__(self) -> None:
        self.istemler: list[str] = []

    async def __call__(self, prompt, deps, **kwargs):
        self.istemler.append(prompt)
        return AgentOutcome(final_text=_PLAN, messages=[], model_calls_made=1)


def _deps(tmp_path, domains: DomainRegistry | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        tool_context=ToolContext(root=tmp_path),
        domains=domains if domains is not None else default_domain_registry(),
    )


async def test_godot_projesinde_plan_istemi_alan_kosullarini_tasir(tmp_path):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    ajan = _IstemKaydedici()

    await generate_plan("zıplamayı düzelt", _deps(tmp_path), ajan, 2, None)

    assert _BASLIK in ajan.istemler[0]
    assert "run/main_scene" in ajan.istemler[0]


async def test_bos_dizinde_godot_adi_gecen_gorev_kosullari_tasir(tmp_path):
    ajan = _IstemKaydedici()

    await generate_plan("Godot ile 2D platform oyunu kur", _deps(tmp_path), ajan, 2, None)

    assert "run/main_scene" in ajan.istemler[0]


async def test_alani_anmayan_gorevde_alan_kosulu_eklenmez(tmp_path):
    ajan = _IstemKaydedici()

    await generate_plan("tarayıcıda çalışan bir oyun yap", _deps(tmp_path), ajan, 2, None)

    assert _BASLIK not in ajan.istemler[0]


async def test_kayittaki_sahte_alanin_kosulu_motor_degismeden_plana_girer(tmp_path):
    (tmp_path / "sahne.blend").write_text("", encoding="utf-8")
    blender = DomainAdapter(
        name="blender", marker="sahne.blend", criteria=("render dosyası diskte ve boş değil",)
    )
    ajan = _IstemKaydedici()

    await generate_plan("sahneyi hazırla", _deps(tmp_path, DomainRegistry((blender,))), ajan, 2, None)

    assert "- render dosyası diskte ve boş değil" in ajan.istemler[0]
    assert "run/main_scene" not in ajan.istemler[0]


def _tek_adimli_plan(hedef: str) -> ExecutionPlan:
    adim = PlanStep(
        step_id="s1",
        goal=hedef,
        depends_on=(),
        expected_effects=("file:a.gd",),
        allowed_tool_families=("files",),
        success_criteria=("dosya yazıldı",),
        verification_hint="",
        retry_safety=RetrySafety.SAFE,
    )
    return ExecutionPlan(plan_id="p", task="iş", steps=(adim,))


def test_dusman_teslimati_genel_listede_degil_godot_alanindadir():
    gorev = "deadcells e benzeyen düşmanlı bir platform yap"
    plan = _tek_adimli_plan("oyuncu hareketini kodla")

    assert missing_deliverables(gorev, plan, domain_deliverables=()) == ()
    assert [
        teslimat.name
        for teslimat in missing_deliverables(
            gorev, plan, domain_deliverables=default_domain_registry().deliverables()
        )
    ] == ["düşman ve dövüş"]
```

- [ ] **Adım 2: Testin düştüğünü gör**

Run: `.venv/bin/pytest tests/test_domain_planning.py -q`
Expected: FAIL — ilk iki test ve sahte alan testi `ALAN KABUL KOŞULLARI` bulamaz; son test
`TypeError: missing_deliverables() got an unexpected keyword argument 'domain_deliverables'`.

- [ ] **Adım 3: İstem şablonunu yaz**

`src/fusion_cli/engines/agent/prompts/domain_acceptance.md`:
```markdown
ALAN KABUL KOŞULLARI — bu işin bittiğini alan açısından bunlar kanıtlar:
{criteria}
Planın başarı koşulları ve doğrulama kontrolleri bu koşulları ölçülebilir biçimde karşılamalı. Karşılanamayan bir koşulu sessizce atlama; planda adıyla belirt.
```

- [ ] **Adım 4: Plan üretimini kayda bağla**

`src/fusion_cli/engines/agent/plan_generation.py`:

Eski:
```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
```
Yeni:
```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
```

`class PlanGeneration` tanımının hemen ALTINA (`async def generate_plan` üstüne) ekle:
```python
#: Plan istem şablonlarının bulunduğu paket dizini.
_PROMPTS = Path(__file__).parent / "prompts"


async def _planning_prompt(
    task: str, deps: AgentDeps, promotion: PromotionContext | None
) -> str:
    """Plan istemini kur: şablon + görev + (varsa) ilgili alanların kabul koşulları.

    Koşullar alan kaydından gelir; motor hangi alanın ne istediğini bilmez. Ölçülen
    boşluk: `acceptance_criteria` hiçbir istemde yoktu ve plan, işin alanda neyle
    bittiğini bilmeden kuruluyordu.
    """
    template = await asyncio.to_thread(
        (_PROMPTS / "execution_plan.md").read_text, encoding="utf-8"
    )
    prompt = template.replace("{task}", task)
    criteria = deps.domains.acceptance_criteria(deps.tool_context.root, task)
    if criteria:
        domain_template = await asyncio.to_thread(
            (_PROMPTS / "domain_acceptance.md").read_text, encoding="utf-8"
        )
        rendered = domain_template.replace(
            "{criteria}", "\n".join(f"- {criterion}" for criterion in criteria)
        )
        prompt = f"{prompt}\n\n{rendered.strip()}"
    if promotion is not None:
        prompt = f"{promotion.render()}\n\n{prompt}"
    return prompt
```

`generate_plan` gövdesinin başı:

Eski:
```python
    import asyncio

    path = Path(__file__).parent / "prompts" / "execution_plan.md"
    template = await asyncio.to_thread(path.read_text, encoding="utf-8")
    prompt = template.replace("{task}", task)
    if promotion is not None:
        prompt = f"{promotion.render()}\n\n{prompt}"
    original_prompt = prompt
```
Yeni:
```python
    prompt = await _planning_prompt(task, deps, promotion)
    original_prompt = prompt
```

Kapsama çağrısı:

Eski:
```python
        eksikler = missing_deliverables(task, plan) if check_coverage else ()
```
Yeni:
```python
        eksikler = (
            missing_deliverables(
                task, plan, domain_deliverables=deps.domains.deliverables()
            )
            if check_coverage
            else ()
        )
```

- [ ] **Adım 5: Genel teslimatları daralt, alan teslimatını parametre yap**

`src/fusion_cli/engines/agent/plan_coverage.py` içinde `DELIVERABLES` demetinden şu iki girdiyi SİL
(`Deliverable(` ile başlayıp `),` ile biten iki blok): `name="düşman ve dövüş"` ve
`name="hikâye / ara sahne"`. Demet yalnız `"dış varlık (asset) edinimi"` ve
`"kullanıcı arayüzü (UI)"` girdileriyle kalır.

`DELIVERABLES` tanımının hemen üstüne yorum ekle:
```python
#: Alandan BAĞIMSIZ teslimatlar. Alana ait olanlar (ör. oyun dövüşü, ara sahne)
#: alan adaptöründe durur ve `missing_deliverables(domain_deliverables=...)` ile gelir.
```

`missing_deliverables`:

Eski:
```python
def missing_deliverables(task: str, plan: ExecutionPlan) -> tuple[Deliverable, ...]:
    """Görevde istenip planda hiç geçmeyen teslimatlar."""
    istek = task.casefold()
    kapsam = _plan_metni(plan)
    return tuple(
        teslimat
        for teslimat in DELIVERABLES
        if any(isaret in istek for isaret in teslimat.request_markers)
        and not any(isaret in kapsam for isaret in teslimat.plan_markers)
    )
```
Yeni:
```python
def missing_deliverables(
    task: str, plan: ExecutionPlan, *, domain_deliverables: tuple[Deliverable, ...]
) -> tuple[Deliverable, ...]:
    """Görevde istenip planda hiç geçmeyen teslimatlar.

    `domain_deliverables` ZORUNLUDUR: varsayılan verilseydi alan bilgisini geçirmeyi
    unutan çağıran, Dead Cells isteğinde düşman adımını sessizce düşürürdü.
    """
    istek = task.casefold()
    kapsam = _plan_metni(plan)
    return tuple(
        teslimat
        for teslimat in (*DELIVERABLES, *domain_deliverables)
        if any(isaret in istek for isaret in teslimat.request_markers)
        and not any(isaret in kapsam for isaret in teslimat.plan_markers)
    )
```

- [ ] **Adım 6: Oyun teslimatlarını Godot alanına ekle**

`src/fusion_cli/engines/agent/domain_adapters/godot.py` import bloğunda:

Eski:
```python
from .contract import DomainAdapter
```
Yeni:
```python
from ..plan_coverage import Deliverable
from .contract import DomainAdapter
```

`_GODOT_IMPORTED_SUFFIXES` tanımının altına ekle (içerik `plan_coverage.py`'dan birebir taşınır):
```python
#: Oyun isteğinin açıkça istediği ama iskelet planların atladığı teslimatlar.
_COMBAT_DELIVERABLE = Deliverable(
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
        "boss",
        "roguelike",
        "hack and slash",
    ),
    plan_markers=("düşman", "enemy", "dövüş", "savaş", "combat", "boss", "hasar"),
    instruction="düşmanları üreten ve oyuncuyla dövüşünü (hasar alma/verme) kuran ayrı bir adım",
)
_STORY_DELIVERABLE = Deliverable(
    name="hikâye / ara sahne",
    request_markers=("ara sahne", "arasahne", "cutscene", "hikaye", "hikâye", "senaryo"),
    plan_markers=("ara sahne", "arasahne", "cutscene", "hikaye", "hikâye", "senaryo"),
    instruction="hikâye metnini ve ara sahne akışını üreten ayrı bir adım",
)
```

`godot_adapter()` içinde:

Eski:
```python
            scripts_without_base,
        ),
    )
```
Yeni:
```python
            scripts_without_base,
        ),
        # Teslimatın kendi `request_markers` alanı "açıkça istendi mi" kapısıdır;
        # kayıt bunları eşleşmeden bağımsız toplar (boş dizindeki oyun isteği).
        deliverables=(_COMBAT_DELIVERABLE, _STORY_DELIVERABLE),
    )
```

- [ ] **Adım 7: Mevcut kapsama testlerini alan teslimatıyla güncelle**

`tests/test_plan_coverage.py` import bloğu:

Eski:
```python
from fusion_cli.core.execution_plan import ExecutionPlan, PlanStep, RetrySafety
from fusion_cli.engines.agent.plan_coverage import (
    coverage_instruction,
    missing_deliverables,
)
```
Yeni:
```python
from types import SimpleNamespace

from fusion_cli.core.execution_plan import ExecutionPlan, PlanStep, RetrySafety
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.domain_adapters.defaults import default_domain_registry
from fusion_cli.engines.agent.plan_coverage import (
    coverage_instruction,
    missing_deliverables,
)

#: Varsayılan kaydın alan teslimatları (düşman/dövüş, hikâye/ara sahne Godot alanında).
_ALAN = default_domain_registry().deliverables()


def _plan_deps(tmp_path) -> SimpleNamespace:
    return SimpleNamespace(tool_context=ToolContext(root=tmp_path), domains=default_domain_registry())
```

Aşağıdaki satırları birebir değiştir (her biri dosyada tek geçer):

| Eski | Yeni |
|---|---|
| `    eksikler = missing_deliverables(GOREV, plan)` | `    eksikler = missing_deliverables(GOREV, plan, domain_deliverables=_ALAN)` |
| `    assert missing_deliverables(gorev, plan) == ()` | `    assert missing_deliverables(gorev, plan, domain_deliverables=_ALAN) == ()` |
| `    eksikler = missing_deliverables(GOREV, _plan(_adim("implement", "Kodla")))` | `    eksikler = missing_deliverables(GOREV, _plan(_adim("implement", "Kodla")), domain_deliverables=_ALAN)` |
| `    assert [t.name for t in missing_deliverables(DEADCELLS_GOREVI, plan)] == ["düşman ve dövüş"]` | `    assert [t.name for t in missing_deliverables(DEADCELLS_GOREVI, plan, domain_deliverables=_ALAN)] == ["düşman ve dövüş"]` |
| `    assert missing_deliverables(DEADCELLS_GOREVI, plan) == ()` | `    assert missing_deliverables(DEADCELLS_GOREVI, plan, domain_deliverables=_ALAN) == ()` |
| `    assert missing_deliverables(gorev, _plan(_adim("fix", "Hatayı düzelt"))) == ()` | `    assert missing_deliverables(gorev, _plan(_adim("fix", "Hatayı düzelt")), domain_deliverables=_ALAN) == ()` |

`assert missing_deliverables(GOREV, plan) == ()` iki kez geçer (`test_kapsayan_plan_eksik_bildirmez`,
`test_kapsam_basari_kosulundan_da_okunur`); ikisini de
`assert missing_deliverables(GOREV, plan, domain_deliverables=_ALAN) == ()` yap.

`generate_plan` testleri:

Eski:
```python
async def test_eksik_kapsam_onarim_istemiyle_yeniden_sorulur(monkeypatch):
```
Yeni:
```python
async def test_eksik_kapsam_onarim_istemiyle_yeniden_sorulur(monkeypatch, tmp_path):
```
Eski:
```python
async def test_onarim_da_eksik_kalirsa_plan_calisir_ama_eksik_bildirilir(monkeypatch):
```
Yeni:
```python
async def test_onarim_da_eksik_kalirsa_plan_calisir_ama_eksik_bildirilir(monkeypatch, tmp_path):
```
Eski:
```python
async def test_yeniden_planlamada_kapsama_kapisi_calismaz():
```
Yeni:
```python
async def test_yeniden_planlamada_kapsama_kapisi_calismaz(tmp_path):
```
Eski (iki kez geçer, ikisi de değişir):
```python
        GOREV, object(), _sahte_agent, 4, None, check_coverage=True
```
Yeni:
```python
        GOREV, _plan_deps(tmp_path), _sahte_agent, 4, None, check_coverage=True
```
Eski:
```python
    sonuc = await plan_generation.generate_plan(GOREV, object(), _sahte_agent, 4, None)
```
Yeni:
```python
    sonuc = await plan_generation.generate_plan(GOREV, _plan_deps(tmp_path), _sahte_agent, 4, None)
```
Satır 100 karakteri aşarsa `ruff format tests/test_plan_coverage.py` ile biçimlendir.

- [ ] **Adım 8: Testlerin geçtiğini gör**

Run: `.venv/bin/pytest tests/test_domain_planning.py tests/test_plan_coverage.py tests/test_plan_step_splitting.py tests/test_plan_runner.py tests/test_plan_parser_tolerance.py -q`
Expected: hepsi PASS; `test_iskelet_plan_uc_teslimatin_eksikligini_bildirir` sırayı
`[asset, UI, hikâye / ara sahne]` olarak korur (genel teslimatlar önce, alan teslimatları sonra).

- [ ] **Adım 9: Kalite kapısı**

Run: `.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest -q`
Expected: üçü temiz.

- [ ] **Adım 10: Commit**

```bash
git add src/fusion_cli/engines/agent/prompts/domain_acceptance.md \
  src/fusion_cli/engines/agent/plan_generation.py \
  src/fusion_cli/engines/agent/plan_coverage.py \
  src/fusion_cli/engines/agent/domain_adapters/godot.py \
  tests/test_plan_coverage.py tests/test_domain_planning.py
git commit -m "feat(plan): alan kabul koşullarını plana ver, oyun teslimatlarını godot alanına taşı"
```

---

### Görev 6: Web alanı — `index.html` yerel kaynaklarının diskte varlığı

**Dosyalar:**
- Modify: `src/fusion_cli/engines/agent/domain_adapters/web.py`
- Test: `tests/test_web_domain_adapter.py`
- DEĞİŞMEZ: `src/fusion_cli/engines/agent/verification.py::WebVerifier`, `web_verify.py`

**Arayüzler:**
- Tüketir: `DomainAdapter.artifact_checks`, `AgentDeps.domains` (Görev 4).
- Üretir: `missing_local_references(root: Path) -> tuple[str, ...]`; `web_adapter()` bu denetimi
  `artifact_checks` olarak taşır (`artifact_suffixes` boş → yalnız kökte `index.html` varken).

- [ ] **Adım 1: Başarısız testi yaz**

`tests/test_web_domain_adapter.py`:
```python
"""Web alanı: `index.html`'in bağladığı yerel dosyalar gerçekten diskte mi?

Metin kapısı (`WebVerifier`) yalnız dokunulan dosyaların METNİNE bakar; sayfanın
`<script src="app.js">` ile bağladığı dosyanın hiç yazılmadığını göremez. Sayfa
açılır, konsol hatası tarayıcı olmadan görünmez ve teslim sessizce bozuktur.

Kök-mutlak yollar (`/src/main.tsx`) sunucu/paketleyiciye göre çözülür (Vite `public/`);
onlar hakkında iddia edilmez. `package.json` tek başına web kanıtı değildir.
"""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.core.execution_plan import ExecutionPlan, PlanStep, RetrySafety, StepStatus
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.domain_adapters.defaults import default_domain_registry
from fusion_cli.engines.agent.domain_adapters.web import missing_local_references
from fusion_cli.engines.agent.loop import AgentDeps
from fusion_cli.engines.agent.step_verification import verify_plan_acceptance

from .fakes import AlwaysApprove, make_config


def _sayfa(tmp_path, govde: str) -> None:
    (tmp_path / "index.html").write_text(
        f"<!doctype html><html><head>{govde}</head><body><main></main></body></html>",
        encoding="utf-8",
    )


def test_bagli_ama_yazilmamis_betik_bulgu_uretir(tmp_path):
    _sayfa(tmp_path, '<script src="app.js"></script><link rel="stylesheet" href="css/stil.css">')
    (tmp_path / "app.js").write_text("", encoding="utf-8")

    bulgular = missing_local_references(tmp_path)

    assert len(bulgular) == 1
    assert "css/stil.css" in bulgular[0]


def test_sorgu_ve_capa_eki_yol_sayilmaz(tmp_path):
    _sayfa(tmp_path, '<script src="./app.js?v=2#x"></script><img src="gorsel%20bir.png">')
    (tmp_path / "app.js").write_text("", encoding="utf-8")
    (tmp_path / "gorsel bir.png").write_bytes(b"x")

    assert missing_local_references(tmp_path) == ()


def test_uzak_mutlak_gomulu_ve_sablon_kaynaklari_denetlenmez(tmp_path):
    _sayfa(
        tmp_path,
        '<script type="module" src="/src/main.tsx"></script>'
        '<link rel="preconnect" href="https://fonts.gstatic.com">'
        '<script src="//cdn.example.com/x.js"></script>'
        '<img src="data:image/svg+xml;utf8,<svg></svg>">'
        '<link rel="icon" href="{{ favicon }}">'
        '<img data-src="tembel.png">'
        '<a href="hakkinda.html">Hakkında</a>',
    )

    assert missing_local_references(tmp_path) == ()


def test_yalniz_package_json_web_kaniti_sayilmaz(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": {"build": "vite build"}}', encoding="utf-8")

    assert default_domain_registry().artifact_findings(tmp_path) == ()


class _Publisher:
    def publish(self, event):
        del event


async def test_final_kabul_kayip_yerel_kaynakta_duser(tmp_path):
    _sayfa(tmp_path, '<script src="oyun.js"></script>')
    adim = PlanStep(
        step_id="sayfa",
        goal="sayfayı yaz",
        depends_on=(),
        expected_effects=("file:index.html",),
        allowed_tool_families=("files",),
        success_criteria=("sayfa var",),
        verification_hint="",
        retry_safety=RetrySafety.SAFE,
    )
    plan = ExecutionPlan("p", "iş", (replace(adim, status=StepStatus.COMPLETED),))
    deps = AgentDeps(
        config=make_config(),
        publisher=_Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )

    sonuc = await verify_plan_acceptance(plan, deps)

    assert sonuc.ok is False
    assert "oyun.js" in sonuc.summary
```

- [ ] **Adım 2: Testin düştüğünü gör**

Run: `.venv/bin/pytest tests/test_web_domain_adapter.py -q`
Expected: FAIL — `ImportError: cannot import name 'missing_local_references'`.

- [ ] **Adım 3: Denetimi yaz ve web adaptörüne bağla**

`src/fusion_cli/engines/agent/domain_adapters/web.py` dosyasının TAMAMI:
```python
"""Web alanı — sayfa gerçekten yükleniyor ve bağladığı yerel dosyalar var.

İşaret kökteki `index.html`'dir. `package.json` tek başına web kanıtı DEĞİLDİR:
CLI araçları, kütüphaneler ve sunucular da onu taşır.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

from .contract import DomainAdapter

#: Sayfanın YÜKLEDİĞİ kaynaklar. `<a href>` dışarıda: gezinme hedefi bir rota olabilir.
_RESOURCE_REFERENCE = re.compile(
    r"""<(?:script|img|link|source|audio|video)\b[^>]*?\s(?:src|href)\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
#: Yerel dosya olarak ÇÖZÜLEMEYEN başlangıçlar.
_NON_LOCAL_PREFIXES = ("#", "/", "data:", "blob:", "javascript:", "mailto:", "tel:")
#: Sunucu tarafı/şablon ifadeleri: gerçek yol çalışma anında belirlenir.
_TEMPLATE_TOKENS = ("{{", "{%", "<%", "${")


def missing_local_references(root: Path) -> tuple[str, ...]:
    """Kökteki `index.html`'in bağladığı göreli yerel dosyalardan diskte olmayanlar.

    Kök-mutlak (`/x`) yollar denetlenmez: sunucu/paketleyici onları farklı dizinden
    (ör. Vite `public/`) sunar ve yokluk iddiası yanlış pozitif olurdu.
    """
    try:
        html = (root / "index.html").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ()
    findings: list[str] = []
    references = dict.fromkeys(match.group(1).strip() for match in _RESOURCE_REFERENCE.finditer(html))
    for reference in references:
        local_path = _local_path(reference)
        if local_path is None or (root / local_path).exists():
            continue
        findings.append(
            f"index.html: `{reference}` yerel kaynağı diskte YOK; sayfa bu dosya olmadan "
            "açılır ve sessizce bozulur. Dosyayı üret ya da yolu `list_dir` ile doğrulayıp düzelt."
        )
    return tuple(findings)


def _local_path(reference: str) -> str | None:
    """Referans göreli bir yerel dosyaysa sorgu/çapa ekinden arınmış yolu; değilse `None`."""
    if not reference or reference.startswith(_NON_LOCAL_PREFIXES) or "://" in reference:
        return None
    if any(token in reference for token in _TEMPLATE_TOKENS):
        return None
    path = unquote(reference.split("#", 1)[0].split("?", 1)[0])
    return path or None


def web_adapter() -> DomainAdapter:
    """Web kanıt sözleşmesi."""
    return DomainAdapter(
        name="web",
        marker="index.html",
        criteria=(
            "sayfa tarayıcıda hatasız yükleniyor",
            "konsolda hata yok",
            "kritik kullanıcı akışı tıklanabiliyor",
        ),
        task_markers=("html", "web sayfası", "web sitesi", "website", "landing page"),
        artifact_checks=(missing_local_references,),
    )
```
(`//cdn…` referansı `/` önekiyle yakalanır; `ruff format` uzun satırları böler.)

- [ ] **Adım 4: Testlerin geçtiğini gör**

Run: `.venv/bin/pytest tests/test_web_domain_adapter.py tests/test_domain_defaults.py tests/test_web_build_runs.py tests/test_classify_verify.py -q`
Expected: hepsi PASS.

- [ ] **Adım 5: Kalite kapısı**

Run: `.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest -q`
Expected: üçü temiz. Mevcut bir test, `index.html`'i gerçekten var olmayan bir göreli dosyaya bağladığı
için düşerse testi gevşetme: kullanıcıya dosya/test adını ve bulgu metnini bildir, onay bekle.

- [ ] **Adım 6: Commit**

```bash
git add src/fusion_cli/engines/agent/domain_adapters/web.py tests/test_web_domain_adapter.py
git commit -m "feat(web): index.html yerel kaynaklarının diskte varlığını final kabulde denetle"
```

---

### Görev 7: Sahte Blender ve medya alanlarıyla genişleme kanıtı

**Dosyalar:**
- Test: `tests/test_domain_extension.py` (üretim kodu DEĞİŞMEZ — kabul testi)

**Arayüzler:**
- Tüketir: `DomainAdapter`, `DomainRegistry`, `build_verifier(..., domains=)`,
  `verify_plan_acceptance` + `AgentDeps.domains`, `generate_plan`.
- Üretir: yok.

- [ ] **Adım 1: Kabul testini yaz**

`tests/test_domain_extension.py`:
```python
"""Yeni alan eklemek motor değişikliği gerektirmez (master belge §14 Faz 1, §16/2).

İki sahte alan yalnız kayıt defterine eklenir ve GERÇEK motor yollarından geçer:

- Blender: kapı keşiften gelir, sıfır çıkışla basılan hata `build_verifier` kapısını
  düşürür, hatasız çıktı geçer; kabul koşulu plan istemine girer.
- Medya: çıktı dosyasının gerçekliği final kabulde (`verify_plan_acceptance`) ölçülür;
  API başarısı değil, diskteki dosya kanıttır.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from fusion_cli.core.evidence import EvidenceStatus
from fusion_cli.core.execution_plan import ExecutionPlan, PlanStep, RetrySafety, StepStatus
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.domain_adapters.contract import DomainAdapter
from fusion_cli.engines.agent.domain_adapters.registry import DomainRegistry
from fusion_cli.engines.agent.loop import AgentDeps, AgentOutcome
from fusion_cli.engines.agent.plan_generation import generate_plan
from fusion_cli.engines.agent.step_verification import verify_plan_acceptance
from fusion_cli.engines.agent.verification import build_verifier

from .fakes import AlwaysApprove, make_config


def _blender(cikti: str) -> DomainAdapter:
    return DomainAdapter(
        name="blender",
        marker="sahne.blend",
        gates=(f"blender() {{ echo '{cikti}'; }}; blender --background --python-exit-code 1",),
        executable="blender",
        output_failure_markers=("error: python", "traceback"),
        criteria=("render çıktısı diskte ve boş değil",),
        task_markers=("blender",),
    )


def _medya_cikti_denetimi(kok: Path) -> tuple[str, ...]:
    cikti = kok / "cikti" / "video.mp4"
    if cikti.is_file() and cikti.stat().st_size > 0:
        return ()
    return ("medya çıktısı yok ya da boş: cikti/video.mp4",)


_MEDYA = DomainAdapter(
    name="medya",
    marker="medya.json",
    artifact_suffixes=(".mp4",),
    artifact_checks=(_medya_cikti_denetimi,),
)


def _config():
    return make_config(runtime={"web_verification": False, "browser_verification": False})


async def test_blender_hatasi_sifir_cikisa_ragmen_kapıyı_dusurur(tmp_path):
    (tmp_path / "sahne.blend").write_text("", encoding="utf-8")
    kayit = DomainRegistry((_blender("Error: Python: Traceback (most recent call last)"),))

    dogrulayici = build_verifier(_config(), root=tmp_path, tool_context=None, domains=kayit)

    assert dogrulayici is not None
    sonuc = await dogrulayici.verify()
    assert sonuc.ok is False
    assert sonuc.evidence[0].status is EvidenceStatus.FAILED


async def test_hatasiz_blender_ciktisi_kapidan_gecer(tmp_path):
    (tmp_path / "sahne.blend").write_text("", encoding="utf-8")
    kayit = DomainRegistry((_blender("Blender 4.2 render tamam"),))

    dogrulayici = build_verifier(_config(), root=tmp_path, tool_context=None, domains=kayit)

    assert dogrulayici is not None
    sonuc = await dogrulayici.verify()
    assert sonuc.ok is True
    assert sonuc.evidence[0].status is EvidenceStatus.PASSED


async def test_blender_kabul_kosulu_plan_istemine_girer(tmp_path):
    istemler: list[str] = []
    plan_json = json.dumps(
        {
            "plan_id": "p1",
            "task": "iş",
            "steps": [
                {
                    "step_id": "s1",
                    "goal": "render al",
                    "depends_on": [],
                    "expected_effects": ["file:render.png"],
                    "allowed_tool_families": ["files"],
                    "success_criteria": ["render yazıldı"],
                    "verification_hint": "",
                    "retry_safety": "safe",
                }
            ],
        },
        ensure_ascii=False,
    )

    async def ajan(prompt, deps, **kwargs):
        istemler.append(prompt)
        return AgentOutcome(final_text=plan_json, messages=[], model_calls_made=1)

    deps = SimpleNamespace(
        tool_context=ToolContext(root=tmp_path),
        domains=DomainRegistry((_blender("hazır"),)),
    )

    await generate_plan("Blender'da ürün render'ı al", deps, ajan, 2, None)

    assert "render çıktısı diskte ve boş değil" in istemler[0]


class _Publisher:
    def publish(self, event):
        del event


def _medya_deps(kok: Path) -> AgentDeps:
    deps = AgentDeps(
        config=make_config(),
        publisher=_Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=kok),
    )
    deps.domains = DomainRegistry((_MEDYA,))
    return deps


def _medya_plani() -> ExecutionPlan:
    adim = PlanStep(
        step_id="uret",
        goal="videoyu üret",
        depends_on=(),
        expected_effects=("file:medya.json",),
        allowed_tool_families=("files",),
        success_criteria=("iş kaydı var",),
        verification_hint="",
        retry_safety=RetrySafety.SAFE,
    )
    return ExecutionPlan("medya", "video üret", (replace(adim, status=StepStatus.COMPLETED),))


async def test_medya_ciktisi_yoksa_final_kabul_duser(tmp_path):
    (tmp_path / "medya.json").write_text('{"durum": "succeeded"}', encoding="utf-8")

    sonuc = await verify_plan_acceptance(_medya_plani(), _medya_deps(tmp_path))

    assert sonuc.ok is False
    assert "cikti/video.mp4" in sonuc.summary


async def test_gercek_medya_ciktisi_final_kabulden_gecer(tmp_path):
    (tmp_path / "medya.json").write_text('{"durum": "succeeded"}', encoding="utf-8")
    (tmp_path / "cikti").mkdir()
    (tmp_path / "cikti" / "video.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")

    sonuc = await verify_plan_acceptance(_medya_plani(), _medya_deps(tmp_path))

    assert sonuc.ok is True
```

- [ ] **Adım 2: Testi çalıştır**

Run: `.venv/bin/pytest tests/test_domain_extension.py -q`
Expected: 5 passed. Bu bir KABUL testidir; Görev 1-6 doğruysa ilk çalıştırmada geçer. Düşerse üretim
kodunda eksik bağlantı var demektir: hatayı sahiplenen modülde (keşif → `verify_discovery.py`, işaret →
`verification.py`, kabul → `step_verification.py`, istem → `plan_generation.py`) düzelt, testi değiştirme.
Kanıtın sahte olmadığını göstermek için geçici olarak `_medya_cikti_denetimi` gövdesini
`return ()` yapıp `test_medya_ciktisi_yoksa_final_kabul_duser`'in düştüğünü gör, sonra geri al.

- [ ] **Adım 3: Kalite kapısı**

Run: `.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest -q`
Expected: üçü temiz.

- [ ] **Adım 4: Commit**

```bash
git add tests/test_domain_extension.py
git commit -m "test(alan): sahte blender ve medya alanlarıyla motor değişmeden genişleme kanıtı"
```

---

### Görev 8: Motor çekirdeğinde alana özgü ad kalmadığını mimari testle kilitle

**Dosyalar:**
- Test: `tests/test_domain_architecture.py`

**Arayüzler:**
- Tüketir: Görev 3-5 sonrası kaynak dosyalar.
- Üretir: yok.

- [ ] **Adım 1: Mimari testi yaz**

`tests/test_domain_architecture.py`:
```python
"""Ortak motor Godot terimlerine bağımlı değildir (master belge §16/1).

Kod düzeyinde (tanımlayıcı, import, docstring OLMAYAN metin sabiti) alana özgü ad
aranır. Yorumlar ve docstring'ler serbesttir: ölçüm hikâyeleri orada kalır.

Bilinen borç sayıyla kilitlidir: `loop.py` MCP araç hatası ipucunda iki kez `'res://'`
örneği veriyor. Borç azalırsa bu test de güncellenmek ZORUNDADIR (sessiz geri dönüş
olmasın diye), artarsa test düşer.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

_PAKET = Path(__file__).resolve().parent.parent / "src" / "fusion_cli"

_MOTOR_MODULLERI = (
    "engines/agent/loop.py",
    "engines/agent/plan_runner.py",
    "engines/agent/step_verification.py",
    "engines/agent/plan_generation.py",
    "engines/agent/verification.py",
    "engines/agent/plan_coverage.py",
    "engines/agent/domain_adapters/contract.py",
    "engines/agent/domain_adapters/registry.py",
)

_ALANA_OZGU = re.compile(r"godot|gdscript|tscn|\.tres\b|res://|cross_file", re.IGNORECASE)

_BILINEN_BORC: Counter[tuple[str, str]] = Counter({("engines/agent/loop.py", "res://"): 2})


def _docstring_dugumleri(agac: ast.AST) -> set[int]:
    kimlikler: set[int] = set()
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if dugum.body and isinstance(dugum.body[0], ast.Expr):
            deger = dugum.body[0].value
            if isinstance(deger, ast.Constant) and isinstance(deger.value, str):
                kimlikler.add(id(deger))
    return kimlikler


def _kod_metinleri(agac: ast.AST) -> list[str]:
    docstringler = _docstring_dugumleri(agac)
    metinler: list[str] = []
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Constant) and isinstance(dugum.value, str):
            if id(dugum) not in docstringler:
                metinler.append(dugum.value)
        elif isinstance(dugum, ast.Name):
            metinler.append(dugum.id)
        elif isinstance(dugum, ast.Attribute):
            metinler.append(dugum.attr)
        elif isinstance(dugum, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            metinler.append(dugum.name)
        elif isinstance(dugum, ast.arg):
            metinler.append(dugum.arg)
        elif isinstance(dugum, ast.ImportFrom):
            metinler.append(dugum.module or "")
            metinler.extend(ad.name for ad in dugum.names)
        elif isinstance(dugum, ast.Import):
            metinler.extend(ad.name for ad in dugum.names)
    return metinler


def _ihlaller() -> Counter[tuple[str, str]]:
    sayac: Counter[tuple[str, str]] = Counter()
    for goreli in _MOTOR_MODULLERI:
        agac = ast.parse((_PAKET / goreli).read_text(encoding="utf-8"))
        for metin in _kod_metinleri(agac):
            for eslesme in _ALANA_OZGU.finditer(metin):
                sayac[(goreli, eslesme.group(0).casefold())] += 1
    return sayac


def test_motor_cekirdeginde_alana_ozgu_ad_yalniz_kayitli_borc_kadardir():
    assert _ihlaller() == _BILINEN_BORC


def test_tarayici_alana_ozgu_adi_gercekten_yakalar():
    """Tarayıcı kör olursa üstteki test anlamsızca geçer; sahte kaynakla sınanır."""
    kaynak = (
        '"""godot docstring serbesttir."""\n'
        "from ...core.cross_file import scene_script_conflicts\n"
        "def godot_kapisi(tscn_yolu):\n"
        "    return 'godot --headless'\n"
    )

    metinler = " ".join(_kod_metinleri(ast.parse(kaynak)))

    assert "cross_file" in metinler
    assert "godot_kapisi" in metinler
    assert "tscn_yolu" in metinler
    assert "godot --headless" in metinler
    assert "docstring serbesttir" not in metinler
```

- [ ] **Adım 2: Testi çalıştır**

Run: `.venv/bin/pytest tests/test_domain_architecture.py -q`
Expected: 2 passed. İlk test düşerse çıktıdaki `(modül, ad)` sayacı hangi motor dosyasında alana özgü ad
kaldığını söyler; adı ilgili adaptör modülüne taşı (Görev 3-5'in eksik kalan kısmıdır). Borcu artırarak
testi geçirme.

Kanıtın kör olmadığını görmek için geçici olarak `step_verification.py`'ye
`_GECICI = "godot"` satırını ekle, ilk testin düştüğünü gör, satırı sil.

- [ ] **Adım 3: Kalite kapısı**

Run: `.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest -q`
Expected: üçü temiz.

- [ ] **Adım 4: Commit**

```bash
git add tests/test_domain_architecture.py
git commit -m "test(mimari): motor çekirdeğinde alana özgü ad kalmadığını denetle"
```

---

### Görev 9: Uçtan uca doğrulama ve sonuç raporu

**Dosyalar:** yok (salt doğrulama; commit yok).

- [ ] **Adım 1: Tam kalite kapısı**

Run: `.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest -q`
Expected: üçü temiz; test sayısı Görev 0'daki sayı + yeni testler.

- [ ] **Adım 2: Korunan davranışları hedefli koş**

Run: `.venv/bin/pytest tests/test_domains.py tests/test_domain_adapters.py tests/test_godot_setup_gate.py tests/test_godot_silent_failures.py tests/test_cross_file_consistency.py tests/test_verification_gate.py tests/test_verify_discovery.py tests/test_plan_coverage.py tests/test_diagnosis_wiring.py -q`
Expected: hepsi PASS; bu dosyalardan yalnız `test_plan_coverage.py` değişmiş olmalı.

Run: `git diff --stat 5ef1453 -- tests/test_domains.py tests/test_domain_adapters.py tests/test_godot_setup_gate.py tests/test_godot_silent_failures.py tests/test_verification_gate.py tests/test_verify_discovery.py`
Expected: çıktı BOŞ (Godot testleri hiç değiştirilmedi).

- [ ] **Adım 3: Katman sınırlarını denetle**

Run: `grep -rn "from \.\.\+engines\|import fusion_cli.engines" src/fusion_cli/core src/fusion_cli/tools | grep -v "memory/lessons"`
Expected: yeni satır yok (bilinen `memory.lessons → engines.verify_discovery` borcu `core`/`tools`
dışında olduğu için listede görünmez).

- [ ] **Adım 4: Kullanıcıya rapor**

Rapor şunları içerir: commit listesi (`git log --oneline 5ef1453..HEAD`), tam kapı sonucu, eklenen test
sayısı, korunan davranış kanıtları (Adım 2), mimari testteki sayılı borç ve aşağıdaki "2b'ye kalanlar".
Push yapılmaz.

---

## 2b'ye kalanlar (bu planın kapsamı dışında)

- **Görsel kapı ve rollback stratejisi** için tipli sözleşme alanları (master §14 Faz 1 madde 2, §10.3
  `DomainAcceptance.visual_checks/rollback_strategy`): bugün tüketicisi yok; Faz 5 artifact omurgası ve
  Faz 2 capability registry ile birlikte tasarlanmalı (YAGNI).
- `loop.py` MCP araç hatası ipucundaki `'res://'` örneğinin alan-bağımsız ipucu kaynağına taşınması
  (mimari testteki sayılı borç).
- `verify_discovery._KIND_MARKERS` içindeki `godot` kimliğinin kayıttan türetilmesi (ders etiketlerini
  değiştirmemek için bu planda bilinçli olarak dokunulmadı).
- `core/structured_files.py` Godot biçim kurallarının (`_godot_kaynak_denetle`, `_godot_proje_denetle`,
  `_gdscript_denetle`, `_SAHIPLI_BICIMLER`) `tools` katmanını `engines`'e bağlamadan çekirdek bir
  biçim-doğrulayıcı protokolüyle alan paketine açılması.
- `memory.lessons → engines.verify_discovery` katman borcu.
- Blender/medya adaptörlerinin GERÇEK sürümleri (Faz 6/8); bu plan yalnız sahte adaptörle genişleme
  noktasını kanıtlar.
