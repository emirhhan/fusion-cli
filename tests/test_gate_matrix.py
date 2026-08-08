"""Kapı etkileşim matrisi — ÇIKIŞSIZ DURUM aramak.

Faz 1'deki özellik ağı BİLİNEN dokuz zayıf-model davranışını sınar. Bu dosya
bilmediklerimizi arar: çalışma alanının olası durumları ile modelin olası hamleleri
makinece çaprazlanır ve tek bir değişmez sınanır:

    Her durumda modelin YAPABİLECEĞİ en az bir hamle vardır.

Çıkışsız bir durum kilitlenmenin tanımıdır: model ne denerse denesin engellenir,
ilerleme üretmez ve tur ölür. Kullanıcının gördüğü "3 turdur ilerleme yok" budur.

Matris yeni kapı eklendiğinde de korur: bir kapı yanlışlıkla son çıkışı kapatırsa
buradaki testler kırılır. Kapıları tek tek doğru yazmak yetmiyor — bugüne kadarki
kilitlenmelerin hepsi kapıların ETKİLEŞİMİNDEN doğdu.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from fusion_cli.core.budget import TurnBudget
from fusion_cli.core.clock import SystemClock
from fusion_cli.core.events import ToolExecuted, ToolOutcome
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import Message, ToolCall
from fusion_cli.engines.agent.approval import Decision
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.loop import _run_tools, _State
from fusion_cli.tools import build_registry

VAR_OLAN = "mevcut.py"
VAR_OLAN_ICERIK = "def eski():\n    return 1\n"
YENI = "yeni.py"


class _Publisher:
    def __init__(self) -> None:
        self.events: list[object] = []

    def publish(self, event: object) -> None:
        self.events.append(event)

    @property
    def son_sonuc(self) -> ToolOutcome | None:
        araclar = [olay for olay in self.events if isinstance(olay, ToolExecuted)]
        return araclar[-1].outcome if araclar else None

    @property
    def son_cikti(self) -> str:
        araclar = [olay for olay in self.events if isinstance(olay, ToolExecuted)]
        return araclar[-1].output if araclar else ""


class _Allow:
    async def decide(self, _request: object) -> Decision:
        return Decision.ALLOW


def _budget() -> TurnBudget:
    return TurnBudget(
        clock=SystemClock(),
        max_model_calls=50,
        max_verify_rounds=2,
        max_empty_retries=2,
        max_contract_repairs=4,
        max_auto_continues=1,
        max_idle_rounds=3,
    )


def _deps(tmp_path: Path, budget: TurnBudget) -> SimpleNamespace:
    return SimpleNamespace(
        publisher=_Publisher(),
        tool_context=ToolContext(tmp_path),
        policy=_Allow(),
        allowed_commands=frozenset(),
        budget=budget,
        require_budget=lambda: budget,
    )


# --------------------------------------------------------------------------- #
# Çalışma alanı DURUMLARI — her biri kapıları farklı bir konfigürasyona sokar
# --------------------------------------------------------------------------- #


def durum_bos_dizin(tmp_path: Path, deps: SimpleNamespace, budget: TurnBudget) -> None:
    """Hiçbir şey yok. En sade durum."""


def durum_dosya_var_okunmamis(
    tmp_path: Path, deps: SimpleNamespace, budget: TurnBudget
) -> None:
    """Kullanıcının dosyası var ama agent onu hiç okumadı — toptan yazma kapalı."""
    (tmp_path / VAR_OLAN).write_text(VAR_OLAN_ICERIK, encoding="utf-8")


def durum_dosya_var_okunmus(tmp_path: Path, deps: SimpleNamespace, budget: TurnBudget) -> None:
    """Dosya okunmuş: toptan yazma açılmış olmalı."""
    hedef = tmp_path / VAR_OLAN
    hedef.write_text(VAR_OLAN_ICERIK, encoding="utf-8")
    deps.tool_context.fully_read.add(hedef.resolve())


def durum_agent_bu_turda_olusturdu(
    tmp_path: Path, deps: SimpleNamespace, budget: TurnBudget
) -> None:
    """İskele senaryosu: dosyayı agent'ın kendisi yazdı, doldurabilmeli."""
    hedef = tmp_path / VAR_OLAN
    deps.tool_context.changes.record(hedef.resolve())
    hedef.write_text("YER TUTUCU\n", encoding="utf-8")


def durum_okuma_tekrarlanmis(
    tmp_path: Path, deps: SimpleNamespace, budget: TurnBudget
) -> None:
    """Aynı okuma iki kez yapılmış: tekrar kapısı üçüncüyü engelleyecek."""
    (tmp_path / VAR_OLAN).write_text(VAR_OLAN_ICERIK, encoding="utf-8")
    imza = budget.signature("read_file", f'{{"path": "{VAR_OLAN}"}}', mutating=False)
    budget.count_call(imza)
    budget.count_call(imza)


def durum_onarim_hakki_bitmis(
    tmp_path: Path, deps: SimpleNamespace, budget: TurnBudget
) -> None:
    """Sözleşme onarım hakkı tükenmiş — bozuk çağrı artık onarılmayacak."""
    (tmp_path / VAR_OLAN).write_text(VAR_OLAN_ICERIK, encoding="utf-8")
    while budget.take_contract_repair():
        pass


def durum_mutasyon_yapilmis(
    tmp_path: Path, deps: SimpleNamespace, budget: TurnBudget
) -> None:
    """Çalışma alanı değişmiş: tekrar imzaları tazelenmiş olmalı."""
    (tmp_path / VAR_OLAN).write_text(VAR_OLAN_ICERIK, encoding="utf-8")
    imza = budget.signature("read_file", f'{{"path": "{VAR_OLAN}"}}', mutating=False)
    budget.count_call(imza)
    budget.count_call(imza)
    budget.record_mutation()


def durum_bos_dizin_tekrarli_listeleme(
    tmp_path: Path, deps: SimpleNamespace, budget: TurnBudget
) -> None:
    """Boş dizinde keşif tükenmiş: model listeleyip durdu, hâlâ bir çıkışı olmalı."""
    imza = budget.signature("list_dir", '{"path": "."}', mutating=False)
    budget.count_call(imza)
    budget.count_call(imza)


DURUMLAR: tuple[tuple[str, Callable[..., None]], ...] = (
    ("bos_dizin", durum_bos_dizin),
    ("dosya_var_okunmamis", durum_dosya_var_okunmamis),
    ("dosya_var_okunmus", durum_dosya_var_okunmus),
    ("agent_bu_turda_olusturdu", durum_agent_bu_turda_olusturdu),
    ("okuma_tekrarlanmis", durum_okuma_tekrarlanmis),
    ("onarim_hakki_bitmis", durum_onarim_hakki_bitmis),
    ("mutasyon_yapilmis", durum_mutasyon_yapilmis),
    ("bos_dizin_tekrarli_listeleme", durum_bos_dizin_tekrarli_listeleme),
)


# --------------------------------------------------------------------------- #
# Modelin deneyebileceği HAMLELER
# --------------------------------------------------------------------------- #


def _cagri(name: str, **args: object) -> ToolCall:
    import json

    return ToolCall(id=f"c_{name}", name=name, arguments=json.dumps(args))


HAMLELER: tuple[tuple[str, Callable[[], ToolCall]], ...] = (
    ("var_olani_oku", lambda: _cagri("read_file", path=VAR_OLAN)),
    ("dizini_listele", lambda: _cagri("list_dir", path=".")),
    ("desen_ara", lambda: _cagri("glob", pattern="**/*.py")),
    ("metin_ara", lambda: _cagri("search_code", pattern="def")),
    ("yeni_dosya_yaz", lambda: _cagri("write_file", path=YENI, content="yeni içerik\n")),
    (
        "var_olani_yaz",
        lambda: _cagri("write_file", path=VAR_OLAN, content="yeni tam içerik\n"),
    ),
    (
        "var_olani_duzenle",
        lambda: _cagri("edit_file", path=VAR_OLAN, old="return 1", new="return 2"),
    ),
    ("todo_yaz", lambda: _cagri("todo_write", todos=[{"content": "adım", "status": "pending"}])),
)


async def _dene(
    tmp_path: Path, kurulum: Callable[..., None], hamle: Callable[[], ToolCall]
) -> tuple[ToolOutcome | None, str]:
    """Tek bir hamleyi, verilen durumdaki KAPI YIĞININDAN geçir."""
    budget = _budget()
    deps = _deps(tmp_path, budget)
    kurulum(tmp_path, deps, budget)

    state = _State()
    messages: list[Message] = []
    execution = ExecutionPolicy(is_web=True, max_same_tool_without_change=2)
    await _run_tools(
        (hamle(),), messages, deps, build_registry(), state, execution=execution
    )
    return deps.publisher.son_sonuc, deps.publisher.son_cikti


# --------------------------------------------------------------------------- #
# ANA DEĞİŞMEZ — hiçbir durum çıkışsız olamaz
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("durum_adi", "kurulum"), DURUMLAR)
async def test_her_durumda_yasal_bir_hamle_vardir(durum_adi, kurulum, tmp_path):
    """Çıkışsız durum = kilitlenme. Her durumda en az bir hamle ÇALIŞMALI."""
    calisanlar: list[str] = []
    engellenenler: list[str] = []

    for hamle_adi, hamle in HAMLELER:
        # Her hamle TEMİZ bir kopyada denenir: hamleler birbirini etkilememeli.
        alan = tmp_path / hamle_adi
        alan.mkdir()
        sonuc, _ = await _dene(alan, kurulum, hamle)
        if sonuc is ToolOutcome.OK:
            calisanlar.append(hamle_adi)
        else:
            engellenenler.append(f"{hamle_adi}({sonuc})")

    assert calisanlar, (
        f"[{durum_adi}] ÇIKIŞSIZ DURUM — modelin hiçbir hamlesi çalışmıyor. "
        f"Engellenenler: {engellenenler}"
    )


@pytest.mark.parametrize(("durum_adi", "kurulum"), DURUMLAR)
async def test_her_durumda_kesif_hamlesi_calisir(durum_adi, kurulum, tmp_path):
    """Model kilitlendiğinde ilk çaresi KEŞİFTİR; keşif her durumda açık kalmalı.

    Sadece "bir hamle çalışıyor" yetmez: çalışan tek hamle yıkıcı bir yazma ise
    model güvenli çıkışa sahip değildir.
    """
    kesif = {"dizini_listele", "desen_ara", "metin_ara"}
    calisan_kesif: list[str] = []

    for hamle_adi, hamle in HAMLELER:
        if hamle_adi not in kesif:
            continue
        alan = tmp_path / hamle_adi
        alan.mkdir()
        sonuc, _ = await _dene(alan, kurulum, hamle)
        if sonuc is ToolOutcome.OK:
            calisan_kesif.append(hamle_adi)

    assert calisan_kesif, f"[{durum_adi}] hiçbir keşif aracı çalışmıyor — model kör kalır"


@pytest.mark.parametrize(("durum_adi", "kurulum"), DURUMLAR)
async def test_her_durumda_yeni_dosya_yazilabilir(durum_adi, kurulum, tmp_path):
    """Yeni dosya yazmak hiçbir kapı tarafından engellenmemeli.

    Toptan-yazma kısıtının gerekçesi VAR OLAN kodu korumaktır; var olmayan bir
    dosyada korunacak bir şey yoktur. Bu yol kapanırsa üretim tamamen durur.
    """
    alan = tmp_path / "yeni"
    alan.mkdir()
    sonuc, cikti = await _dene(alan, kurulum, dict(HAMLELER)["yeni_dosya_yaz"])

    assert sonuc is ToolOutcome.OK, f"[{durum_adi}] yeni dosya yazılamadı: {cikti}"


#: Bir engelleme mesajının çıkış yolu saydığı işaretler: somut araç adı ya da
#: modelin yapabileceği açık bir eylem.
_CIKIS_ISARETLERI = (
    "read_file",
    "edit_file",
    "multi_edit",
    "write_file",
    "list_dir",
    "glob",
    "search_code",
    "ask_user",
    "run_shell",
    "sonraki adım",
    "farklı",
    "söyle",
    "doğrula",
    "bul",
)


@pytest.mark.parametrize(("durum_adi", "kurulum"), DURUMLAR)
async def test_matriste_her_engelleme_cikis_yolu_gosterir(durum_adi, kurulum, tmp_path):
    """Çıkışsız mesaj, çıkışsız durumun habercisidir.

    Durum × hamle çaprazının TAMAMI taranır: bir kapı eklendiğinde ya da bir mesaj
    değiştirildiğinde modele "peki şimdi ne yapayım" sorusunu cevapsız bırakırsa
    burada görülür. Kilitlenmelerin kök sebebi buydu.
    """
    cikissiz: list[str] = []

    for hamle_adi, hamle in HAMLELER:
        alan = tmp_path / hamle_adi
        alan.mkdir()
        sonuc, cikti = await _dene(alan, kurulum, hamle)
        if sonuc is ToolOutcome.OK or not cikti:
            continue
        if not any(isaret in cikti for isaret in _CIKIS_ISARETLERI):
            cikissiz.append(f"{hamle_adi}: {cikti[:160]}")

    assert not cikissiz, f"[{durum_adi}] çıkış yolu göstermeyen engelleme(ler):\n" + "\n".join(
        cikissiz
    )


# --------------------------------------------------------------------------- #
# KORUMALAR — matris gevşemeyi de yakalamalı
# --------------------------------------------------------------------------- #


async def test_okunmamis_var_olan_dosya_korunur(tmp_path):
    """Çıkış açmak KORUMAYI gevşetmemeli: kör toptan yazma engellenmeye devam eder."""
    alan = tmp_path / "kor"
    alan.mkdir()
    sonuc, cikti = await _dene(alan, durum_dosya_var_okunmamis, dict(HAMLELER)["var_olani_yaz"])

    assert sonuc is not ToolOutcome.OK
    assert "zaten var" in cikti
    assert "edit_file" in cikti, "engelleme çıkış yolu göstermeli"


async def test_web_modelinde_okumak_toptan_yazmayi_acmaz(tmp_path):
    """Koruma İKİ KATMANLI ve katmanlar farklı kuralda — bu bilinçli.

    `files.py` "önce oku" der ve okunmuş dosyada yolu açar. Motor katmanı ise web
    modellerinde var olan bir dosyanın toptan yazılmasını okunmuş olsa da kapatır:
    ölçüldü, yıkıcı başarısızlıkların HEPSİNDE `write_file` vardı ve zayıf model yüz
    satırlık hata yüzeyini temiz geçemiyor. Sıkı olan katman kazanır.

    Bu test o katmanlamayı KİLİTLER: biri gevşetilirse burada görülür.
    """
    alan = tmp_path / "okundu"
    alan.mkdir()
    sonuc, cikti = await _dene(alan, durum_dosya_var_okunmus, dict(HAMLELER)["var_olani_yaz"])

    assert sonuc is not ToolOutcome.OK
    assert "edit_file" in cikti


async def test_api_modelinde_okunmus_dosya_toptan_yazilabilir(tmp_path):
    """Motor kısıtı YALNIZCA web modellerine aittir; API modelinde yol açıktır."""
    alan = tmp_path / "api"
    alan.mkdir()
    budget = _budget()
    deps = _deps(alan, budget)
    durum_dosya_var_okunmus(alan, deps, budget)

    await _run_tools(
        (dict(HAMLELER)["var_olani_yaz"](),),
        [],
        deps,
        build_registry(),
        _State(),
        execution=ExecutionPolicy(is_web=False),
    )

    assert deps.publisher.son_sonuc is ToolOutcome.OK, deps.publisher.son_cikti


async def test_api_modelinde_okunmamis_dosya_yine_korunur(tmp_path):
    """API modelinde de kör yazma yasak: `files.py` katmanı her sağlayıcıda çalışır."""
    alan = tmp_path / "api-kor"
    alan.mkdir()
    budget = _budget()
    deps = _deps(alan, budget)
    durum_dosya_var_okunmamis(alan, deps, budget)

    await _run_tools(
        (dict(HAMLELER)["var_olani_yaz"](),),
        [],
        deps,
        build_registry(),
        _State(),
        execution=ExecutionPolicy(is_web=False),
    )

    assert deps.publisher.son_sonuc is not ToolOutcome.OK
    assert "okumadın" in deps.publisher.son_cikti


async def test_agentin_kendi_olusturdugu_dosya_doldurulabilir(tmp_path):
    """İskele ölü kilidi matriste de kapalı kalmalı."""
    alan = tmp_path / "iskele"
    alan.mkdir()
    sonuc, cikti = await _dene(
        alan, durum_agent_bu_turda_olusturdu, dict(HAMLELER)["var_olani_yaz"]
    )

    assert sonuc is ToolOutcome.OK, cikti


async def test_mutasyondan_sonra_tekrar_sayaci_tazelenir(tmp_path):
    """Çalışma alanı değiştiyse aynı dosyayı yeniden okumak MEŞRUDUR."""
    alan = tmp_path / "tazelenme"
    alan.mkdir()
    sonuc, cikti = await _dene(alan, durum_mutasyon_yapilmis, dict(HAMLELER)["var_olani_oku"])

    assert sonuc is ToolOutcome.OK, f"mutasyondan sonra okuma engellendi: {cikti}"


async def test_tekrarlanan_okuma_mutasyon_yokken_engellenir(tmp_path):
    """Karşı yön: değişiklik olmadan üçüncü kez okumak hâlâ engellenir."""
    alan = tmp_path / "tekrar"
    alan.mkdir()
    sonuc, cikti = await _dene(alan, durum_okuma_tekrarlanmis, dict(HAMLELER)["var_olani_oku"])

    assert sonuc is not ToolOutcome.OK
    assert "TOOL_CALL_DUPLICATE" in cikti
