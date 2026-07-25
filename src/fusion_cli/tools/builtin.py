"""Yerleşik araçların kayıt defteri — şemaların tanımlandığı TEK yer.

Yeni bir araç eklemek: executor'ı ilgili modüle yaz, buraya bir `Tool` kaydı ekle.
Motor kodu, onay akışı ve render katmanı değişmez.

Açıklama metinleri modele yazılmıştır: aracın ne yaptığını değil, NE ZAMAN
seçileceğini anlatır. Model doğru aracı seçemezse en iyi executor bile işe yaramaz.
"""

from __future__ import annotations

from ..core.tools import Tool
from . import files, planning, search, shell, web
from .registry import ToolRegistry

#: JSON Schema parçası. İç içe geçtiği için değer tipi serbest bırakılır; bu yapı
#: modele olduğu gibi gönderilen bir sözlüktür, iş mantığı taşımaz.
SchemaFragment = dict[str, object]


def _schema(properties: dict[str, SchemaFragment], required: list[str]) -> SchemaFragment:
    return {"type": "object", "properties": properties, "required": required}


_STRING: SchemaFragment = {"type": "string"}


def build_registry() -> ToolRegistry:
    """Yerleşik araçların tamamını içeren yeni bir kayıt defteri üret."""
    registry = ToolRegistry()
    for tool in _TOOLS:
        registry.register(tool)
    for alias, target in _ALIASES.items():
        registry.register_alias(alias, target)
    return registry


_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="read_file",
        description="Bir dosyanın içeriğini satır numaralarıyla oku. Bir dosyayı "
        "değiştirmeden ÖNCE mutlaka oku; kör düzenleme yapma.",
        parameters=_schema({"path": {**_STRING, "description": "Dosya yolu"}}, ["path"]),
        run=files.read_file,
    ),
    Tool(
        name="write_file",
        description="Bir dosyayı verilen içerikle oluştur ya da TAMAMEN üzerine yaz. "
        "Var olan bir dosyanın bir kısmını değiştireceksen bunu değil edit_file kullan.",
        parameters=_schema(
            {
                # Açıklamada sıra vurgulanır: içerik büyükse model küçük alanı sona
                # bırakıp bazen hiç üretmiyor ve tur boşa gidiyor.
                "path": {**_STRING, "description": "Dosya yolu. İLK bu alanı yaz."},
                "content": {
                    **_STRING,
                    "description": "Dosyanın yeni tam içeriği. 'path' YAZILDIKTAN SONRA gelir.",
                },
            },
            ["path", "content"],
        ),
        run=files.write_file,
        mutating=True,
    ),
    Tool(
        name="edit_file",
        description="Bir dosyada birebir eşleşen 'old' metnini 'new' ile değiştir. "
        "'old' dosyada BENZERSİZ olmalı; değilse çevresinden birkaç satır daha ekle.",
        parameters=_schema(
            {
                "path": _STRING,
                "old": {**_STRING, "description": "Değiştirilecek mevcut metin (benzersiz)"},
                "new": {**_STRING, "description": "Yeni metin"},
            },
            ["path", "old", "new"],
        ),
        run=files.edit_file,
        mutating=True,
    ),
    Tool(
        name="multi_edit",
        description="Tek dosyada birden çok old→new değişikliğini SIRAYLA ve ATOMİK uygula "
        "(biri tutmazsa hiçbiri uygulanmaz). Aynı dosyada çok yer değişecekse bunu kullan.",
        parameters=_schema(
            {
                "path": _STRING,
                "edits": {
                    "type": "array",
                    "description": "[{'old': 'benzersiz metin', 'new': 'yeni metin'}, …]",
                    "items": _schema({"old": _STRING, "new": _STRING}, ["old", "new"]),
                },
            },
            ["path", "edits"],
        ),
        run=files.multi_edit,
        mutating=True,
    ),
    Tool(
        name="list_dir",
        description="Bir dizindeki dosya ve klasörleri listele. Projeyi tanımak için "
        "önce bunu kullan, körlemesine dosya okuma.",
        parameters=_schema({"path": {**_STRING, "description": "Dizin yolu (varsayılan: .)"}}, []),
        run=files.list_dir,
    ),
    Tool(
        name="search_code",
        description="Bir dizinde metin/regex ara (grep gibi). KESİN bir metni ya da "
        "deseni ararken kullan.",
        parameters=_schema(
            {
                "pattern": {**_STRING, "description": "Aranacak metin veya regex"},
                "path": {**_STRING, "description": "Dizin/dosya (varsayılan: .)"},
            },
            ["pattern"],
        ),
        run=search.search_code,
    ),
    Tool(
        name="glob",
        description="Dosya adı deseniyle dosya bul (ör. '**/*.py'). Belirli tipteki "
        "dosyaları toplarken search_code'dan hızlıdır.",
        parameters=_schema(
            {
                "pattern": {**_STRING, "description": "glob deseni, ör. '**/*.py'"},
                "path": {**_STRING, "description": "kök dizin (varsayılan: .)"},
            },
            ["pattern"],
        ),
        run=search.glob_files,
    ),
    Tool(
        name="git",
        description="Salt-okunur git komutu çalıştır (status, diff, log, branch, show…). "
        "Onay gerektirmez. Commit/push gibi değiştirici git için run_shell kullan.",
        parameters=_schema(
            {
                "subcommand": {
                    **_STRING,
                    "description": "ör: 'status', 'diff', 'log --oneline -5'",
                }
            },
            ["subcommand"],
        ),
        run=shell.git,
    ),
    Tool(
        name="run_shell",
        description="Bir kabuk komutu çalıştır ve çıktısını al. Kod değiştirdiysen "
        "test/lint/build çalıştırarak işini DOĞRULA. Değiştirici — onay gerekir.",
        parameters=_schema({"command": _STRING}, ["command"]),
        run=shell.run_shell,
        mutating=True,
    ),
    Tool(
        name="todo_write",
        description="Görev listesini TAMAMEN güncelle. Çok adımlı işlerde plan çıkar ve "
        "ilerledikçe güncelle (bir maddeyi in_progress yap, bitince completed). "
        "Basit tek adımlı işlerde kullanma.",
        parameters=_schema(
            {
                "todos": {
                    "type": "array",
                    "items": _schema(
                        {
                            "content": _STRING,
                            "status": {
                                **_STRING,
                                "enum": ["pending", "in_progress", "completed"],
                            },
                        },
                        ["content", "status"],
                    ),
                }
            },
            ["todos"],
        ),
        run=planning.todo_write,
    ),
    Tool(
        name="web_search",
        description="Web'de ara (ücretsiz, anahtarsız). Güncel bilgi, sürüm değişikliği "
        "ya da hata mesajı çözümü gerektiğinde kullan; ezberden emin konuşma.",
        parameters=_schema({"query": {**_STRING, "description": "arama sorgusu"}}, ["query"]),
        run=web.web_search,
    ),
    Tool(
        name="web_fetch",
        description="Bir URL'nin içeriğini çek ve metnini oku (HTML temizlenir). "
        "web_search sonucundaki bir sayfayı okumak için kullan.",
        parameters=_schema({"url": _STRING}, ["url"]),
        run=web.web_fetch,
    ),
)

#: Bazı modeller bu adları tercih eder; farklı isimlendirme alışkanlığı hataya dönüşmesin.
_ALIASES = {
    "view_file": "read_file",
    "grep_search": "search_code",
    "read_url_content": "web_fetch",
}
