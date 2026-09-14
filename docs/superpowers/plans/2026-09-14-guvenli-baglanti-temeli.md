# Güvenli Bağlantı Temeli — Uygulama Planı

> **Ajanlar için:** Bu plan görev görev uygulanır (superpowers:subagent-driven-development
> veya superpowers:executing-plans). Adımlar `- [ ]` ile işaretlenir.

**Kaynak:** `FUSION_MASTER_PROJE_DOKUMANI.md` (Faz 0 + Faz 2'nin güvenlik ön koşulu) ve
ChatGPT/Codex oturumu `01a09c88…` — "Fusion projesi MD dokümanı oluştur". Codex bu oturumda
kullanıcının "bu isteklerimin tümünü anlayıp yap" onayıyla üç salt-okunur inceleme yaptı ve
uygulama ajanlarını başlatırken kullanım limitine takıldı; hiçbir dosya değişmedi. Bu plan o
incelemenin bulgularından devam eder.

**Amaç:** Reklam, WordPress/Novamira, Meshy, Higgsfield gibi dış sistemler bağlanmadan ÖNCE,
uzak bir MCP aracının otomatik onay kipinde (auto) kullanıcıya sorulmadan değişiklik yapmasını
engellemek ve stdio MCP sunucularına kayıtlı ortam değişkenlerini gerçekten ulaştırmak.

**Neden önce bu:** Kodda doğrulandı (14 Eylül 2026, HEAD `20a7d40`):

1. `mcp_bridge/client.py::register_into` her uzak aracı `mutating=True` kaydediyor, fakat
   `engines/agent/approval.py::build_request` kabuk dışı araçlara `danger=None` ve
   `unattended_safe=True` veriyor. `AutoApproval.decide` bu ikisini görünce **sormadan izin
   veriyor**. Yani auto kipte bir reklam MCP'sinin "bütçeyi değiştir" veya bir WordPress
   MCP'sinin "sayfayı sil" aracı kullanıcı görmeden çalışır. Belgedeki "harcama, yayın ve silme
   açık onay ister" ilkesi (§2.1, §13.6, §16/10-11) bugün sağlanmıyor.
2. `mcp_bridge/transport.py::open_mcp_stream` `StdioServerParameters` kurarken `env=`
   vermiyor. MCP SDK 1.29.1 `stdio_client` bu durumda yalnız `get_default_environment()`
   (HOME, PATH vb.) aktarıyor; `McpServerConfig.env_names` ile kaydedilen API anahtarları
   sunucu sürecine hiç ulaşmıyor.

**Mimari:** Yeni motor veya yeni onay yolu açılmaz. `core/tools.py::Tool`'a aracın etki sınıfını
söyleyen tek bir alan (`effect`) eklenir. `build_request` bu alanı mevcut `danger` ve
`unattended_safe` alanlarına çevirir, böylece `AutoApproval`, `SecurityApproval` ve
`PlanApproval` sınıfları değişmeden doğru kararı verir. MCP köprüsü etki sınıfını MCP araç
açıklamalarından (`ToolAnnotations`) üretir.

**Teknoloji:** Python 3.11+, MCP Python SDK 1.29.1, pytest (asyncio), ruff, mypy.

## Genel Kısıtlar

- `CLAUDE.md` ve `RULES.md` bağlayıcıdır; deponun `.env` dosyası okunmaz.
- Çalışılan dal: `fusion-runtime-hardening-20260827-022831` (38 commit ileride; yeni dal açılmaz, dal değiştirilmez).
- İzlenmeyen kullanıcı dosyalarına dokunulmaz: `:memory:.ses`, `dagitim/`, `index.html`, `FUSION_MASTER_PROJE_DOKUMANI.md`.
- Docstring, yorum, hata ve kullanıcı metinleri Türkçe; tanımlayıcılar İngilizce.
- `core` stdlib dışında bir şey import etmez.
- Her görev RED → GREEN testle yapılır; test adı `test_<konu>_<beklenen davranış>`.
- Commit: Türkçe conventional commit, faz numarası ve co-author satırı YOK, push YOK.
- Commit öncesi kalite kapısı: `.venv/bin/ruff check .`, `.venv/bin/mypy`, `.venv/bin/pytest -q`.

## MCP açıklamalarına güven kararı

MCP şartnamesi ve SDK (`mcp/types.py::ToolAnnotations`) açıklamaların **ipucu** olduğunu, güvenilmeyen
sunucudan gelen ipucuyla araç kararı verilmemesi gerektiğini söylüyor. Bu plan ipucunu yalnız
**sıkılaştırmak** için kullanır, bir istisna dışında gevşetmek için kullanmaz:

| Açıklama | Etki sınıfı | auto kip | security kip | plan kip |
|---|---|---|---|---|
| Açıklama yok / `readOnlyHint` yok ya da false | `REMOTE_WRITE` | İlk çağrıda sorar; "oturum boyunca" izni hatırlanır | Sorar | Engeller |
| `destructiveHint: true` | `REMOTE_DESTRUCTIVE` | **Her çağrıda** sorar, oturum izni verilmez | Sorar | Engeller |
| `readOnlyHint: true` | `REMOTE_READ` | Sormaz (bugünkü davranış) | Sorar | Engeller |

`REMOTE_READ` istisnası güvenliği bugünden kötüleştirmez: bugün auto kip BÜTÜN uzak araçları
sormadan çalıştırıyor. Yalan söyleyen sunucu zaten kendi tarafında istediğini yapabilir; ipucu
yalnız bir onay sorusunu atlatır. Açıklamasız eski sunucular (ör. Godot MCP) `REMOTE_WRITE`
sayılır; oturum başına araç başına bir kez sorulur, her çağrıda sorulmaz.

---

### Görev 0: Başlangıç durumunu kaydet

**Dosyalar:**
- Oluştur: `docs/superpowers/reports/2026-09-14-platform-baseline.md`

**Arayüzler:** Kod yok. Sonraki fazlar karşılaştırma için bu raporu kullanır.

- [ ] **Adım 1: Git durumunu kaydet**

```bash
git status -sb
git rev-parse --short HEAD
git rev-list --count origin/fusion-runtime-hardening-20260827-022831..HEAD
```

Beklenen: HEAD `20a7d40`, 38 commit ileride, yalnız dört izlenmeyen öğe.

- [ ] **Adım 2: Kalite kapılarını çalıştır**

```bash
.venv/bin/ruff check .
.venv/bin/mypy
.venv/bin/pytest -q
(cd app && npm test)
```

Beklenen (14 Eylül ölçümü): ruff "All checks passed!", mypy "no issues found in 330 source
files", pytest ve frontend sonuçları rapora olduğu gibi yazılır. Kırmızı bir kapı varsa plan
DURUR ve kullanıcıya bildirilir; kırık baseline üstüne kod yazılmaz.

- [ ] **Adım 3: Raporu yaz**

Rapor şu başlıkları taşır: tarih, dal, HEAD, remote farkı, izlenmeyen öğeler, her kapının komutu
ve gerçek çıktısı, Codex oturumunda (13 Eylül) bulunan ve bu planın dışında kalan açıklar:

- Composer model seçici rol (`agent`, `judge`, adaylar) listeliyor, model listelemiyor
  (`appserver/commands.py::_model_step`, `app/src/screens/ModelPicker.tsx`).
- `config/model_select.py::set_agent_model` eski görev haritasını ve yetenek etiketlerini koruyor.
- Web tarayıcı taşıması modeli yok sayıyor (`providers/web_browser.py::build_browser_transport`, `del model`).
- `tool_eval_passed` hesap düzeyinde; model/düşünme değişince geçersizleşmiyor.
- `domains.py::adapter_for` üretimde kullanılmıyor; `step_verification.py::verify_plan_acceptance`
  her projede altı Godot kontrolünü doğrudan çağırıyor; `plan_coverage.py` düşman/dövüş
  teslimini global tutuyor.
- `core/artifacts.py::ArtifactStore` sayaç tabanlı ad kullanıyor, ikili artifact/iş devamı yok.
- `appserver/session.py` 1.100+ satır; RULES.md 400 satır sınırını aşıyor.

- [ ] **Adım 4: Commit**

```bash
git add docs/superpowers/reports/2026-09-14-platform-baseline.md
git commit -m "docs: platform dönüşümü öncesi başlangıç durumunu kaydet"
```

---

### Görev 1: Araç etki sınıfı ve onay kararı

**Dosyalar:**
- Değiştir: `src/fusion_cli/core/tools.py` (`ToolFamily` enum'undan sonra `ToolEffect`; `Tool` dataclass'ına `effect` alanı)
- Değiştir: `src/fusion_cli/engines/agent/approval.py:139-154` (`build_request`)
- Test: `tests/test_agent_approval.py`

**Arayüzler:**
- Üretir: `fusion_cli.core.tools.ToolEffect` (`LOCAL`, `REMOTE_READ`, `REMOTE_WRITE`, `REMOTE_DESTRUCTIVE`)
- Üretir: `Tool.effect: ToolEffect = ToolEffect.LOCAL`
- Üretir: `fusion_cli.engines.agent.approval.REMOTE_DESTRUCTIVE_REASON: str`
- Değişmez: `ApprovalRequest`, `AutoApproval`, `SecurityApproval`, `PlanApproval`, `build_policy`

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/test_agent_approval.py` başına import ve yardımcıyı güncelle:

```python
from fusion_cli.core.tools import Tool, ToolEffect
from fusion_cli.engines.agent.approval import (
    REMOTE_DESTRUCTIVE_REASON,
    ApprovalAnswer,
    ApprovalMode,
    Decision,
    build_policy,
    build_request,
)

from .fakes import AlwaysApprove, AlwaysReject


def _arac(ad="write_file", *, mutating=True, effect=ToolEffect.LOCAL):
    return Tool(
        name=ad,
        description="",
        parameters={},
        run=lambda a, c: None,
        mutating=mutating,
        effect=effect,
    )
```

Dosyanın sonuna ekle:

```python
class _SayanOnayci:
    """Kaç kez sorulduğunu sayan ve sabit cevap veren sahte kullanıcı."""

    def __init__(self, cevap):
        self.cevap = cevap
        self.soru_sayisi = 0

    async def confirm(self, request):
        self.soru_sayisi += 1
        return self.cevap


async def test_auto_modda_uzak_yazma_araci_sorulmadan_calismaz():
    politika = build_policy(ApprovalMode.AUTO, AlwaysReject())

    karar = await politika.decide(
        build_request(_arac("ads__update_budget", effect=ToolEffect.REMOTE_WRITE), {})
    )

    assert karar is Decision.DENIED


async def test_auto_modda_uzak_yazma_oturum_izniyle_bir_kez_sorulur():
    onayci = _SayanOnayci(ApprovalAnswer.SESSION)
    politika = build_policy(ApprovalMode.AUTO, onayci)
    arac = _arac("godot__add_node", effect=ToolEffect.REMOTE_WRITE)

    ilk = await politika.decide(build_request(arac, {"name": "a"}))
    ikinci = await politika.decide(build_request(arac, {"name": "b"}))

    assert (ilk, ikinci) == (Decision.ALLOW, Decision.ALLOW)
    assert onayci.soru_sayisi == 1


async def test_auto_modda_yikici_uzak_arac_her_cagride_sorulur():
    onayci = _SayanOnayci(ApprovalAnswer.SESSION)
    politika = build_policy(ApprovalMode.AUTO, onayci)
    arac = _arac("wp__delete_page", effect=ToolEffect.REMOTE_DESTRUCTIVE)

    await politika.decide(build_request(arac, {"id": 1}))
    await politika.decide(build_request(arac, {"id": 2}))

    assert onayci.soru_sayisi == 2


def test_yikici_uzak_arac_istegi_gerekceyi_tasir():
    istek = build_request(_arac("wp__delete_page", effect=ToolEffect.REMOTE_DESTRUCTIVE), {})

    assert istek.danger == REMOTE_DESTRUCTIVE_REASON


async def test_auto_modda_salt_okunur_uzak_arac_sorulmaz():
    politika = build_policy(ApprovalMode.AUTO, AlwaysReject())

    karar = await politika.decide(
        build_request(_arac("ads__get_insights", effect=ToolEffect.REMOTE_READ), {})
    )

    assert karar is Decision.ALLOW


async def test_security_modda_salt_okunur_uzak_arac_yine_sorulur():
    politika = build_policy(ApprovalMode.SECURITY, AlwaysReject())

    karar = await politika.decide(
        build_request(_arac("ads__get_insights", effect=ToolEffect.REMOTE_READ), {})
    )

    assert karar is Decision.DENIED


def test_arac_etkisi_varsayilan_olarak_yereldir():
    arac = Tool(name="read_file", description="", parameters={}, run=lambda a, c: None)

    assert arac.effect is ToolEffect.LOCAL
```

- [ ] **Adım 2: Testlerin başarısız olduğunu gör**

Çalıştır: `.venv/bin/pytest tests/test_agent_approval.py -q`
Beklenen: `ImportError: cannot import name 'ToolEffect'` ile toplama hatası.

- [ ] **Adım 3: `ToolEffect` ve `Tool.effect` ekle**

`src/fusion_cli/core/tools.py` içinde `ToolFamily` sınıfının bittiği yerin hemen altına:

```python
class ToolEffect(Enum):
    """Bir aracın dünyada bıraktığı iz — onay kararının girdisi.

    `mutating` "onay akışına girer mi?" sorusunu cevaplar; bu enum "ne kadar
    sıkı sorulmalı?" sorusunu. Yerel dosya yazımı diff ile görülür ve geri
    alınabilir; uzak sistemdeki bütçe, yayın veya silme işlemi geri alınamayabilir.
    """

    #: Yalnız yerel çalışma alanına dokunur (varsayılan).
    LOCAL = "local"
    #: Uzak sistemi yalnız okur.
    REMOTE_READ = "remote_read"
    #: Uzak sistemde değişiklik yapabilir.
    REMOTE_WRITE = "remote_write"
    #: Uzak sistemde geri alınamaz değişiklik yapabilir (silme, yayın, harcama).
    REMOTE_DESTRUCTIVE = "remote_destructive"
```

`Tool` dataclass'ında `advertised` alanından sonra:

```python
    #: Aracın etki sınıfı; onay politikası uzak ve yıkıcı işlemleri buna göre sıkılaştırır.
    effect: ToolEffect = ToolEffect.LOCAL
```

- [ ] **Adım 4: `build_request`'i etki sınıfına bağla**

`src/fusion_cli/engines/agent/approval.py` import satırını güncelle:

```python
from ...core.tools import Tool, ToolArgs, ToolEffect
```

`class ApprovalMode` tanımından önce:

```python
#: Uzak sistemde geri alınamaz değişiklik yapabilen aracın onay gerekçesi.
REMOTE_DESTRUCTIVE_REASON = (
    "Bu uzak araç kendini geri alınamaz değişiklik yapabilir olarak tanımlıyor "
    "(silme, yayınlama veya harcama). Her çağrıda ayrıca onay istenir."
)

#: Gözetimsiz (auto kipte sormadan) çalışabilecek etki sınıfları.
_UNATTENDED_EFFECTS = frozenset({ToolEffect.LOCAL, ToolEffect.REMOTE_READ})
```

`build_request` gövdesini şununla değiştir:

```python
def build_request(
    tool: Tool, args: ToolArgs, allowed_commands: frozenset[str] = frozenset()
) -> ApprovalRequest:
    """Onay isteğini kur; yıkıcılık tespiti ve izin listesi kontrolü burada yapılır.

    Uzak araçlar kabuk komutu gibi ele alınır: auto kip TANIMADIĞI şeyi sormadan
    yapmaz. Eskiden kabuk dışındaki her araç `unattended_safe=True` sayılıyordu;
    bir reklam MCP'sinin bütçe değiştiren aracı auto kipte kullanıcı görmeden
    çalışabiliyordu.
    """
    command = args.get("command")
    kabuk = tool.name == "run_shell" and isinstance(command, str)
    pre_allowed = kabuk and is_allowed(str(command), allowed_commands)
    danger = danger_reason(tool.name, args)
    if danger is None and tool.effect is ToolEffect.REMOTE_DESTRUCTIVE:
        danger = REMOTE_DESTRUCTIVE_REASON
    return ApprovalRequest(
        tool=tool,
        args=args,
        danger=danger,
        pre_allowed=pre_allowed,
        unattended_safe=(
            is_unattended_safe(str(command)) if kabuk else tool.effect in _UNATTENDED_EFFECTS
        ),
    )
```

`ApprovalRequest.unattended_safe` alanının yorumunu da güncelle:

```python
    #: Çağrı gözetimsiz çalışmaya uygun mu?
    #:
    #: Kabukta tanınan, yan etkisiz komut; kabuk dışında yerel ya da salt okunur
    #: uzak araç. Uzak yazma araçları False'tur ve auto kipte sorulur.
    unattended_safe: bool = True
```

- [ ] **Adım 5: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/pytest tests/test_agent_approval.py tests/test_appserver_bridges.py tests/test_tui_loop.py -q`
Beklenen: hepsi PASS.

- [ ] **Adım 6: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest -q
git add src/fusion_cli/core/tools.py src/fusion_cli/engines/agent/approval.py tests/test_agent_approval.py
git commit -m "fix(onay): uzak araçlar auto kipte sorulmadan çalışmasın"
```

---

### Görev 2: MCP araç açıklamalarını etki sınıfına çevir

**Dosyalar:**
- Oluştur: `src/fusion_cli/mcp_bridge/tool_effect.py`
- Değiştir: `src/fusion_cli/mcp_bridge/client.py` (`RemoteTool`, `list_tools`, `register_into`, modül docstring'inin "Güvenlik" paragrafı)
- Test: `tests/test_mcp_tool_effect.py`, `tests/test_mcp.py`

**Arayüzler:**
- Tüketir: `ToolEffect` (Görev 1)
- Üretir: `fusion_cli.mcp_bridge.tool_effect.effect_from_annotations(annotations: ToolAnnotations | None) -> ToolEffect`
- Üretir: `RemoteTool.effect: ToolEffect = ToolEffect.REMOTE_WRITE`

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/test_mcp_tool_effect.py`:

```python
"""MCP araç açıklamaları → Fusion etki sınıfı."""

from __future__ import annotations

import pytest
from mcp.types import ToolAnnotations

from fusion_cli.core.tools import ToolEffect
from fusion_cli.mcp_bridge.tool_effect import effect_from_annotations


@pytest.mark.parametrize(
    ("annotations", "beklenen"),
    [
        (None, ToolEffect.REMOTE_WRITE),
        (ToolAnnotations(), ToolEffect.REMOTE_WRITE),
        (ToolAnnotations(readOnlyHint=True), ToolEffect.REMOTE_READ),
        (ToolAnnotations(readOnlyHint=True, destructiveHint=True), ToolEffect.REMOTE_READ),
        (ToolAnnotations(readOnlyHint=False, destructiveHint=True), ToolEffect.REMOTE_DESTRUCTIVE),
        (ToolAnnotations(destructiveHint=True), ToolEffect.REMOTE_DESTRUCTIVE),
        (ToolAnnotations(readOnlyHint=False, destructiveHint=False), ToolEffect.REMOTE_WRITE),
    ],
)
def test_mcp_aciklamasi_etki_sinifina_cevrilir(annotations, beklenen):
    assert effect_from_annotations(annotations) is beklenen
```

`tests/test_mcp.py` içinde `_SahteArac`'ı açıklama alacak şekilde güncelle:

```python
class _SahteArac:
    def __init__(self, ad: str, annotations=None) -> None:
        self.name = ad
        self.description = "sahte"
        self.inputSchema = {"type": "object", "properties": {}}
        self.annotations = annotations
```

`test_yinelenen_cursor_sonsuz_dongu_olusturmaz` testinden sonra ekle:

```python
async def test_register_into_mcp_aciklamasini_arac_etkisine_tasir():
    from mcp.types import ToolAnnotations

    from fusion_cli.core.tools import ToolEffect
    from fusion_cli.tools import ToolRegistry

    session = _SayfaliOturum(
        {
            None: SimpleNamespace(
                tools=[
                    _SahteArac("oku", ToolAnnotations(readOnlyHint=True)),
                    _SahteArac("sil", ToolAnnotations(destructiveHint=True)),
                    _SahteArac("yaz"),
                ],
                nextCursor=None,
            )
        }
    )
    client = McpClient(())
    client._sessions["fixture"] = session
    registry = ToolRegistry()

    await client.register_into(registry)

    etkiler = {ad: registry.get(f"fixture__{ad}").effect for ad in ("oku", "sil", "yaz")}
    assert etkiler == {
        "oku": ToolEffect.REMOTE_READ,
        "sil": ToolEffect.REMOTE_DESTRUCTIVE,
        "yaz": ToolEffect.REMOTE_WRITE,
    }
    # Onay akışından çıkarılan uzak araç yok: security kip hepsini sormaya devam eder.
    assert all(registry.get(f"fixture__{ad}").mutating for ad in ("oku", "sil", "yaz"))
```

- [ ] **Adım 2: Testlerin başarısız olduğunu gör**

Çalıştır: `.venv/bin/pytest tests/test_mcp_tool_effect.py tests/test_mcp.py -q`
Beklenen: `ModuleNotFoundError: No module named 'fusion_cli.mcp_bridge.tool_effect'`.

- [ ] **Adım 3: Çeviriciyi yaz**

`src/fusion_cli/mcp_bridge/tool_effect.py`:

```python
"""MCP araç açıklamalarını Fusion'ın onay etki sınıfına çevir.

MCP şartnamesine göre açıklamalar İPUCUDUR ve güvenilmeyen sunucuya dayanarak
gevşek karar verilmez. Bu yüzden ipucu yalnız onayı SIKILAŞTIRMAK için kullanılır;
tek istisna `readOnlyHint`: auto kip bugün zaten bütün uzak araçları sormadan
çalıştırıyordu, salt okunur araç için bu davranış korunur. Security kip hepsini
yine sorar.
"""

from __future__ import annotations

from mcp.types import ToolAnnotations

from ..core.tools import ToolEffect


def effect_from_annotations(annotations: ToolAnnotations | None) -> ToolEffect:
    """Açıklaması olmayan araç yazma sayılır; `destructiveHint` açıkça true ise yıkıcı.

    Şartnamenin varsayılanı `destructiveHint=true`'dur; açıklamasız her aracı yıkıcı
    saymak auto kipte eski sunucuların (ör. Godot MCP) HER çağrısını sorar ve
    otonom koşuları kullanılamaz kılar. Açıklamasız araç oturum başına bir kez sorulur.
    """
    if annotations is None:
        return ToolEffect.REMOTE_WRITE
    if annotations.readOnlyHint is True:
        return ToolEffect.REMOTE_READ
    if annotations.destructiveHint is True:
        return ToolEffect.REMOTE_DESTRUCTIVE
    return ToolEffect.REMOTE_WRITE
```

- [ ] **Adım 4: İstemciyi bağla**

`src/fusion_cli/mcp_bridge/client.py`:

Import'lar:

```python
from ..core.tools import Tool, ToolArgs, ToolContext, ToolEffect, ToolResult
from .tool_effect import effect_from_annotations
```

`RemoteTool`:

```python
@dataclass(slots=True)
class RemoteTool:
    """Uzak bir MCP aracının Fusion'a taşınan tanımı."""

    server: str
    name: str
    description: str
    schema: dict[str, object] = field(default_factory=dict)
    effect: ToolEffect = ToolEffect.REMOTE_WRITE
```

`list_tools` içindeki `RemoteTool(...)` çağrısına:

```python
                    # Sahte ve eski SDK araç nesnelerinde alan olmayabilir.
                    effect=effect_from_annotations(getattr(tool, "annotations", None)),
```

`register_into` içindeki `Tool(...)` çağrısında `mutating=True` satırından sonra:

```python
                        effect=remote.effect,
```

Modül docstring'inin son paragrafını değiştir:

```text
Güvenlik: dış araçlar `mutating=True` kaydedilir, yani onay akışına girerler. Aracın
MCP açıklaması `effect` alanına çevrilir: auto kip uzak yazma araçlarını ilk
çağrıda, yıkıcı araçları her çağrıda sorar (bkz. `tool_effect.py`).
```

- [ ] **Adım 5: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/pytest tests/test_mcp_tool_effect.py tests/test_mcp.py tests/test_mcp_pool.py -q`
Beklenen: hepsi PASS.

- [ ] **Adım 6: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest -q
git add src/fusion_cli/mcp_bridge/tool_effect.py src/fusion_cli/mcp_bridge/client.py tests/test_mcp_tool_effect.py tests/test_mcp.py
git commit -m "feat(mcp): araç açıklamasını onay etki sınıfına çevir"
```

---

### Görev 3: stdio MCP sunucusuna kayıtlı ortam değişkenlerini aktar

**Dosyalar:**
- Değiştir: `src/fusion_cli/mcp_bridge/transport.py` (`resolve_stdio_env` ekle, `open_mcp_stream` stdio dalı)
- Test: `tests/test_mcp.py`

**Arayüzler:**
- Üretir: `fusion_cli.mcp_bridge.transport.resolve_stdio_env(config: McpServerConfig, *, environ: Mapping[str, str] | None = None) -> dict[str, str]`

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/test_mcp.py` import satırını güncelle:

```python
from fusion_cli.mcp_bridge.transport import resolve_stdio_args, resolve_stdio_env
```

`test_stdio_gizli_arguman_eksikse_acik_hata_verir`'den sonra ekle:

```python
def test_stdio_ortam_degiskenleri_yalniz_kayitli_adlarla_aktarilir():
    config = McpServerConfig(name="brave", command="server-brave", env_names=("BRAVE_API_KEY",))

    assert resolve_stdio_env(
        config, environ={"BRAVE_API_KEY": "anahtar", "BASKA_SIR": "gizli"}
    ) == {"BRAVE_API_KEY": "anahtar"}


def test_stdio_kayitli_ortam_degiskeni_eksikse_acik_hata_verir():
    config = McpServerConfig(name="brave", command="server-brave", env_names=("BRAVE_API_KEY",))

    with pytest.raises(ValueError, match="BRAVE_API_KEY"):
        resolve_stdio_env(config, environ={})


async def test_stdio_akisi_ortam_degiskenlerini_sunucu_surecine_verir(monkeypatch):
    from contextlib import asynccontextmanager

    from fusion_cli.mcp_bridge import transport

    yakalanan = {}

    @asynccontextmanager
    async def _sahte_stdio_client(params):
        yakalanan["env"] = params.env
        yield ("okuma", "yazma")

    monkeypatch.setattr(transport, "stdio_client", _sahte_stdio_client)
    monkeypatch.setenv("BRAVE_API_KEY", "anahtar")
    config = McpServerConfig(name="brave", command="server-brave", env_names=("BRAVE_API_KEY",))

    async with transport.open_mcp_stream(config) as akislar:
        assert akislar == ("okuma", "yazma")

    assert yakalanan["env"] == {"BRAVE_API_KEY": "anahtar"}
```

- [ ] **Adım 2: Testlerin başarısız olduğunu gör**

Çalıştır: `.venv/bin/pytest tests/test_mcp.py -q -k stdio`
Beklenen: `ImportError: cannot import name 'resolve_stdio_env'`.

- [ ] **Adım 3: Uygula**

`src/fusion_cli/mcp_bridge/transport.py` içinde `resolve_stdio_args`'tan sonra:

```python
def resolve_stdio_env(
    config: McpServerConfig, *, environ: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Kayıtlı ortam değişkenlerini alt-sürece verilecek sözlüğe çevir.

    MCP SDK `env` verilmezse yalnız HOME, PATH gibi güvenli değişkenleri aktarır.
    Ölçüldü (SDK 1.29.1, `mcp/client/stdio/__init__.py`): bağlantı ekranında girilen
    API anahtarları şifreli depodan ortama yükleniyor ama sunucu sürecine hiç
    ulaşmıyordu. Yalnız `env_names` içindeki adlar aktarılır; Fusion'ın bütün
    ortamı dış sürece açılmaz.
    """
    source = os.environ if environ is None else environ
    eksikler = [name for name in config.env_names if not source.get(name)]
    if eksikler:
        raise ValueError(f"MCP ortam değişkeni bulunamadı: {', '.join(eksikler)}")
    return {name: source[name] for name in config.env_names}
```

`open_mcp_stream` stdio dalında `params` satırını değiştir:

```python
        params = StdioServerParameters(
            command=config.command,
            args=resolve_stdio_args(config),
            # Boş sözlük yerine None: SDK varsayılan ortamı kendisi kurar.
            env=resolve_stdio_env(config) or None,
        )
```

- [ ] **Adım 4: Testlerin geçtiğini gör**

Çalıştır: `.venv/bin/pytest tests/test_mcp.py tests/test_mcp_connect_failures.py tests/test_appserver_connectors.py -q`
Beklenen: hepsi PASS.

- [ ] **Adım 5: Kalite kapısı ve commit**

```bash
.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest -q
git add src/fusion_cli/mcp_bridge/transport.py tests/test_mcp.py
git commit -m "fix(mcp): kayıtlı ortam değişkenlerini stdio sunucusuna aktar"
```

---

### Görev 4: Uçtan uca doğrulama ve sonuç raporu

**Dosyalar:**
- Oluştur: `docs/superpowers/reports/2026-09-14-guvenli-baglanti-temeli-sonuc.md`

- [ ] **Adım 1: Tam kapılar**

```bash
.venv/bin/ruff check .
.venv/bin/mypy
.venv/bin/pytest -q
(cd app && npm test)
```

Beklenen: Görev 0 raporundaki sayılara göre yalnız yeni testler kadar artış, sıfır başarısızlık.

- [ ] **Adım 2: Masaüstünde gerçek onay kartı**

Fusion masaüstünü kaynaktan başlat, auto kipte açıklamasız bir stdio MCP aracını (Fusion'ın
kendi MCP sunucusu: `python -m fusion_cli.mcp_bridge.server <klasör>`) çağıran bir istek
gönder. Beklenen: ilk çağrıda onay kartı görünür; "oturum boyunca" seçilince ikinci çağrı
sorulmaz. Ekran görüntüsü rapora eklenir. Masaüstü açılamazsa bu adım "yapılamadı" diye
yazılır, başarı sayılmaz.

- [ ] **Adım 3: Raporu yaz ve commit**

Rapor: yapılanlar, komut çıktıları, masaüstü kanıtı, bilinen sınırlar (plan kipinin salt okunur
uzak araçları hâlâ engellemesi, UI'da etki rozeti olmaması), sıradaki plan.

```bash
git add docs/superpowers/reports/2026-09-14-guvenli-baglanti-temeli-sonuc.md
git commit -m "docs: güvenli bağlantı temeli sonuç raporunu ekle"
```

---

## Bu planın kapsamı dışında kalanlar (sıradaki planlar)

Belgedeki sıra korunur; her biri ayrı plan ve ayrı onay ister:

1. **DomainAdapter v2 (belge Faz 1):** `adapter_for`'u üretime bağlama, altı Godot kontrolünü
   adaptör kaydına taşıma, kabul ölçütlerini planlayıcıya verme, `plan_coverage`'daki
   oyun teslimlerini alana taşıma, "motor Godot'a bağımlı değil" mimari testi.
2. **Composer'da gerçek model ve düşünme seçimi (belge Faz 3):** rol yerine model listesi, açık
   seçimin yetkili olması, desteklenen düşünme seviyeleri, web modeli seçimi ve model bazlı
   araç ölçümü.
3. **ConnectorManifest/capability kataloğu (belge Faz 2 devamı):** backend manifestlerinden
   gelen bağlantı kataloğu, UI'da etki/risk rozeti, plan kipinde salt okunur uzak araçlar.
4. Async job + artifact omurgası, Fusion Browser eklentisi, Meshy/Blender/Godot, Higgsfield,
   WordPress/Novamira, reklam ve araştırma fazları.
