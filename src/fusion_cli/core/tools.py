"""Araç sözleşmeleri.

Bir araç üç parçadan oluşur ve üçü tek yerde, kayıt defterinde birleşir:
şema (modele ne söyleneceği), executor (işi yapan saf fonksiyon) ve `mutating`
bayrağı (onay gerekip gerekmediği).

Executor SAF tutulur: konsola yazmaz, kullanıcıya sormaz, modül seviyesinde durum
tutmaz. Onay, önizleme ve gösterim aracın dışındadır. Tur bazlı durum (görev listesi
gibi) `ToolContext` üzerinden taşınır — eski projede bu modül-global bir liste olduğu
için alt-ajanlar ana ajanla aynı listeyi paylaşıyordu.

Sonuçlar metin değil `ToolResult` döner: "bu çıktı hata mı?" sorusu string aramasıyla
dağınık biçimde değil, tek bir bayrakla cevaplanır.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from threading import Event
from typing import Protocol

from .artifacts import ArtifactStore
from .browser_session import BrowserSession
from .changeset import ChangeSet
from .tool_content import ToolContent, ToolContentType

#: Modelin araca verdiği ham argümanlar. JSON'dan geldiği için tipsizdir;
#: `tools.args` yardımcıları bunları doğrulayarak okur.
ToolArgs = Mapping[str, object]


class ToolFamily(Enum):
    """Bir aracın ait olduğu iş ailesi.

    İki ayrı yer aynı sözlüğü kullanır: plan şemasındaki `allowed_tool_families`
    alanı ve hızlı turun "ikinci araç ailesi devreye girdi" yükseltme sinyali.
    Sözlük tek yerde tutulmazsa bu iki taraf sessizce ayrışır.
    """

    FILES = "files"
    SEARCH = "search"
    SHELL = "shell"
    VCS = "vcs"
    BROWSER = "browser"
    WEB = "web"
    DELEGATION = "delegation"
    #: MCP sunucuları ve tanımadığımız eklenti araçları.
    EXTERNAL = "external"
    #: Kendi başına iş üretmeyen yardımcılar: görev listesi, soru sorma, hatırlama.
    #: Karmaşıklık kanıtı SAYILMAZ; yoksa "dosya oku + todo yaz" iki aile görünürdü.
    META = "meta"


_TOOL_FAMILIES: Mapping[str, ToolFamily] = {
    "read_file": ToolFamily.FILES,
    "view_file": ToolFamily.FILES,
    "write_file": ToolFamily.FILES,
    "edit_file": ToolFamily.FILES,
    "multi_edit": ToolFamily.FILES,
    "replace_range": ToolFamily.FILES,
    "list_dir": ToolFamily.FILES,
    "list_files": ToolFamily.FILES,
    "create_file": ToolFamily.FILES,
    "glob": ToolFamily.FILES,
    "scaffold_web": ToolFamily.FILES,
    "grep_search": ToolFamily.SEARCH,
    "search_code": ToolFamily.SEARCH,
    "search_codebase": ToolFamily.SEARCH,
    "run_shell": ToolFamily.SHELL,
    "shell": ToolFamily.SHELL,
    "bash": ToolFamily.SHELL,
    "execute_command": ToolFamily.SHELL,
    "git": ToolFamily.VCS,
    "browser_open": ToolFamily.BROWSER,
    "browser_read": ToolFamily.BROWSER,
    "browser_click": ToolFamily.BROWSER,
    "browser_type": ToolFamily.BROWSER,
    "browser_screenshot": ToolFamily.BROWSER,
    "browser_mirror": ToolFamily.BROWSER,
    "browser_close": ToolFamily.BROWSER,
    "web_search": ToolFamily.WEB,
    "web_fetch": ToolFamily.WEB,
    "download_file": ToolFamily.WEB,
    "read_url_content": ToolFamily.WEB,
    "spawn_agent": ToolFamily.DELEGATION,
    "invoke_subagent": ToolFamily.DELEGATION,
    "invoke_agent": ToolFamily.DELEGATION,
    "council": ToolFamily.DELEGATION,
    "todo_write": ToolFamily.META,
    "ask_user": ToolFamily.META,
    "read_session": ToolFamily.META,
    "find_skill": ToolFamily.META,
    "read_skill": ToolFamily.META,
    "find_agent": ToolFamily.META,
}


def tool_family(name: str) -> ToolFamily:
    """Araç adını iş ailesine çevir.

    Tanımadığımız ad yardımcı SAYILMAZ: MCP araçları `<sunucu>__<araç>` biçiminde
    çalışma anında eklenir ve bir eklenti aracının karmaşıklık kanıtını gizlemesi,
    hızlı turun büyüyen işi fark etmemesi demektir.
    """
    return _TOOL_FAMILIES.get(name, ToolFamily.EXTERNAL)


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Bir araç çalıştırmasının sonucu."""

    output: str
    ok: bool = True
    content: tuple[ToolContent, ...] = ()
    structured: Mapping[str, object] | None = None
    #: Çıktı bağlamı şişirdiği için diske alındıysa dosyanın yolu.
    #:
    #: Kırpma bilgiyi yok eder, artifact yalnızca YER DEĞİŞTİRİR: model özeti görür,
    #: gerekirse dosyayı `read_file` ile açar. Kanıt zinciri de bu yolu kullanır.
    artifact_path: str = ""

    @property
    def images(self) -> tuple[str, ...]:
        """Sağlayıcıya aktarılabilir görselleri data URI biçiminde döndür."""
        return tuple(
            block.data_uri
            for block in self.content
            if block.type is ToolContentType.IMAGE and block.data_uri
        )

    @classmethod
    def failure(
        cls,
        message: str,
        *,
        content: tuple[ToolContent, ...] = (),
        structured: Mapping[str, object] | None = None,
    ) -> ToolResult:
        """Aracın kendi tespit ettiği, modele düzeltme şansı veren hata."""
        return cls(output=message, ok=False, content=content, structured=structured)


class TodoStatus(Enum):
    """Bir görev maddesinin durumu."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

    @property
    def icon(self) -> str:
        return {"pending": "☐", "in_progress": "▶", "completed": "☒"}[self.value]


@dataclass(frozen=True, slots=True)
class TodoItem:
    """Görev listesindeki tek madde."""

    content: str
    status: TodoStatus


class TodoList:
    """Tur bazlı görev listesi.

    Modül-global DEĞİLDİR: her tur (ve her alt-ajan) kendi listesine sahiptir.
    """

    def __init__(self) -> None:
        self._items: tuple[TodoItem, ...] = ()

    def replace(self, items: tuple[TodoItem, ...]) -> None:
        self._items = items

    @property
    def items(self) -> tuple[TodoItem, ...]:
        return self._items

    @property
    def has_pending(self) -> bool:
        """Tamamlanmamış madde var mı? (İşin yarım kalıp kalmadığı sezgiseli için.)"""
        return self.pending_count > 0

    @property
    def pending_count(self) -> int:
        """Tamamlanmamış madde sayısı. Devam bütçesi buna göre büyür."""
        return sum(1 for item in self._items if item.status is not TodoStatus.COMPLETED)

    def render(self) -> str:
        return "\n".join(f"{item.status.icon} {item.content}" for item in self._items)


class PendingWrite:
    """`write_file` içeriğinin geçici sakladığı yer.

    Model büyük içerikte sondaki küçük `path` alanını düşürüyor (beş koşuda 14 kez;
    birinde çağrıların yarısı). İçeriği çöpe atmak 15 KB'lık dosyanın baştan
    üretilmesi demekti. Saklanır ve model YALNIZCA yolu göndererek işi bitirir.

    Yol TAHMİN EDİLMEZ: yanlış tahmin var olan bir dosyanın üzerine yazmak demektir.
    """

    def __init__(self) -> None:
        self.content = ""

    def take(self) -> str:
        """Saklanan içeriği al ve temizle: bir kez kullanılır, sonrakine sızmaz."""
        icerik, self.content = self.content, ""
        return icerik


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Araçların çalıştığı ortam. Executor'lar dış dünyaya buradan erişir."""

    #: Göreli yolların çözümleneceği kök dizin.
    root: Path
    #: Bu tura ait görev listesi.
    todos: TodoList = field(default_factory=TodoList)
    #: Agent'ın bu oturumda OLUŞTURDUĞU ya da DEĞİŞTİRDİĞİ dosyalar.
    #:
    #: Doğrulama kapısı yalnızca buraya bakar: kök dizini taramak, agent'ın hiç
    #: dokunmadığı dosyalar hakkında bulgu üretirdi. Yalnızca başarılı yazma iz bırakır.
    touched: set[Path] = field(default_factory=set)
    #: İçeriği TAM olarak okunmuş dosyalar (kırpılmadan).
    #
    # `write_file` dosyanın tamamını değiştirir. Model dosyayı hiç okumadıysa ya da
    # kırpılmış okuduysa, gönderdiği "tam içerik" gerçekten tam DEĞİLDİR ve kesme
    # noktasından sonrası sessizce yok olur. Bu küme o kararı ölçülebilir kılar.
    fully_read: set[Path] = field(default_factory=set)
    #: `read_file` ile görülen dosyaların içerik revision'ı.
    #:
    #: `replace_range` modelden eski içeriği tekrar üretmesini istemez. Bunun güvenli
    #: olabilmesi için satır numaralarının HÂLÂ modelin gördüğü dosyaya ait olduğunu
    #: doğrularız. Revision modele taşınmaz; araç katmanı kendi bildiği okuma durumunu
    #: burada tutar. Böylece tool çağrısı kısa kalır.
    read_revisions: dict[Path, str] = field(default_factory=dict)
    #: `write_file` çağrısında `path` eksik kaldığında içeriğin saklandığı yer.
    #: `ToolContext` frozen olduğu için taşıyıcı nesne kullanılır (todos ile aynı desen).
    pending: PendingWrite = field(default_factory=lambda: PendingWrite())
    #: Tur boyunca açık kalan tarayıcı. Etkileşimli tarayıcı araçları buraya bağlanır:
    #: "alana yaz → gönder → açılan sayfayı oku" üç ayrı çağrıdır ve aynı sayfayı görmeli.
    browser: BrowserSession = field(default_factory=BrowserSession)
    #: True ise dosya araçları yalnızca `root` (ve `extra_roots`) altında çalışır;
    #: dışarı çıkan yol, `..` ile taşan yol ve dışarı sızdıran symlink reddedilir.
    #:
    #: Varsayılan AÇIKTIR. Opt-in bırakıldığı sürece kimse açmıyordu ve agent her
    #: kurulumda kullanıcının tüm dosya sistemine yazabiliyordu; tüm disk hiçbir
    #: aracın varsayılan erişim alanı olmamalıdır. Kök dışına erişim gerekiyorsa
    #: kullanıcı bunu `--add-dir` ile AÇIKÇA verir.
    restrict_to_root: bool = True
    #: Bu turda değiştirilen dosyaların ilk hâlleri — geri alma (`/undo`) için.
    #: `touched` ile aynı desende paylaşılır: alt-ajanın değişikliği de buraya girer.
    changes: ChangeSet = field(default_factory=ChangeSet)
    #: Kökün yanında erişime açılan ek dizinler (`--add-dir`).
    #:
    #: Bir kapı değil, dar bir penceredir: yalnızca burada YAZAN dizinlerin altı
    #: açılır, kardeşleri açılmaz ve symlink ile aşılamaz (yol `resolve` edilir).
    extra_roots: tuple[Path, ...] = ()
    #: İptal edilen turdaki thread tabanlı araçların yürümeye devam etmesini önler.
    cancelled: Event = field(default_factory=Event)
    #: Büyük araç çıktılarının yazılacağı depo; `None` ise kırpma davranışı korunur.
    artifacts: ArtifactStore | None = None
    #: Bu turda bir okumada gösterilecek EN FAZLA satır; `None` ise varsayılan.
    #:
    #: SWE-agent'ın ölçümü: turda ~100 satır göstermek en iyi sonucu veriyor. Sınır
    #: sabit değil TAŞIMAYA bağlıdır: web yolunda bağlam pahalıdır ve uzun okuma
    #: hem gecikme hem context rot üretir; API yolunda mevcut ölçülmüş davranış
    #: (800 satır) korunur. Model `limit` ile bu pencereyi AŞAMAZ; daraltabilir.
    read_window: int | None = None
    #: Bu turda kayıt defterinde bulunan araç adları.
    #:
    #: Yapı denetimi buna bakar: bir biçimi zaten doğru üreten araç varken
    #: modelin o dosyayı elle yazması engellenip araca yönlendirilir. Araç yoksa
    #: elle yazma tek yoldur ve serbest kalır.
    available_tools: set[str] = field(default_factory=set)


#: Bir aracın işini yapan fonksiyon. Saf tutulur; yan etkisi yalnızca dosya
#: sistemi / kabuk / ağ üzerindedir, terminale ya da kullanıcıya değil.
#:
#: Asenkron da olabilir: alt-ajan devri ya da çoklu-model danışma gibi araçlar doğası
#: gereği bekler. Kayıt defteri ikisini de aynı şekilde çalıştırır, çağıran taraf farkı
#: bilmez — bu sayede motorda "şu araç özel" diye bir dal açılmaz.
ToolExecutor = Callable[[ToolArgs, ToolContext], ToolResult | Awaitable[ToolResult]]


@dataclass(frozen=True, slots=True)
class Tool:
    """Şema + executor + onay bayrağı."""

    name: str
    description: str
    #: Modele verilecek JSON Schema (OpenAI function-calling biçimi).
    parameters: Mapping[str, object]
    run: ToolExecutor
    #: True ise araç dosya/sistem durumunu değiştirir ve onay akışına girer.
    mutating: bool = False
    #: False ise araç ÇALIŞIR ama modele sunulan listede görünmez.
    #
    # Takma adlar içindir. `view_file` ile `read_file` aynı şeydir ve ikisi de
    # aynı açıklamayla listelenince model ayırt edilemez iki araç görür; ölçüldü:
    # model aynı dosya için iki adı dönüşümlü kullanıp tekrar kapısına takıldı.
    # Takma ad çağrılırsa yine çalışır — amaç hatayı önlemek, seçenek sunmak değil.
    advertised: bool = True

    def schema(self) -> dict[str, object]:
        """Model çağrısına eklenecek function-calling şeması."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": dict(self.parameters),
            },
        }


class ToolPreviewer(Protocol):
    """Değiştirici bir araç ÇALIŞMADAN önce ne yapacağını anlatan önizleme üretir."""

    def __call__(self, args: ToolArgs, context: ToolContext) -> str | None: ...
