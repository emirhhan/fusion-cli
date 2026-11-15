"""`fusion browser …` — ajan tarayıcısının kullanıcı oturumu profilleri (P-023).

Komutlar ince tutulur: girdiyi çözer, `engines.browser_profiles` akışını çağırır,
sonucu basar. Çerez DEĞERİ hiçbir komut çıktısında yer almaz; yalnız alan adı ve sayı.
Onay: içe aktarma ve silme alan adı listesini/profili gösterir ve `--yes` yoksa TTY'de
sorar; TTY yokken `--yes` zorunludur (sessiz onay yok). Chrome içe aktarma alan adı ister
(`-d` ya da açıkça `--all-domains`): bütün Chrome çerez kavanozu varsayılanla taşınmaz.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from ..config.browser_profiles import (
    SOURCE_FILE,
    BrowserProfileStore,
    BrowserProfileSummary,
    default_browser_profile_store,
)
from ..config.loader import load_config
from ..config.writer import write_browser_setting
from ..core.errors import FusionError
from ..engines.browser_profiles import (
    ImportPreview,
    find_chrome_profile,
    import_chrome_profile,
    import_cookie_file,
    preview_chrome_profile,
    preview_cookie_file,
)
from ..engines.web_session_import import (
    available_web_sessions,
    find_web_session,
    import_web_session,
    preview_web_session,
    validate_domains,
)
from ..providers.chrome_cookies import list_chrome_profiles

app = typer.Typer(
    no_args_is_help=True,
    help="Ajan tarayıcısına kullanıcı oturumu (çerez) profilleri: içe aktar, listele, giriş yap.",
)
console = Console()

_NO_PROFILES = (
    "Kayıtlı tarayıcı profili yok. Örnek: fusion browser import-cookies cookies.txt -p is"
)
_CONFIRM = "Bu alan adlarının çerezleri '{name}' profiline şifreli yazılacak. Devam?"
_NEED_YES = "Etkileşimsiz ortamda onay için --yes gerekir."
_ABORTED = "İptal edildi; hiçbir şey yazılmadı."
_SAVED = "[green]Profil yazıldı:[/green] {name} — {count} çerez, {domains} alan adı"
_DELETED = "[green]Silindi:[/green] {name}"
_NOT_FOUND = "Profil yok: {name}"
_DEFAULT_SET = "[green]Varsayılan profil:[/green] {name}"
_DEFAULT_CLEARED = "[green]Varsayılan profil kaldırıldı;[/green] tarayıcı çerezsiz açılır."
_LOGIN_DONE = "[green]Oturum kaydedildi:[/green] {name} — {count} çerez"
_CHROME_NEED_DOMAIN = (
    "Chrome içe aktarmada alan adı seç (-d example.com) ya da bütün çerezleri bilerek "
    "aktarmak için --all-domains ver. Varsayılanla tüm Chrome oturumları taşınmaz."
)
_SETTING_WRITTEN = "[green]browser.{key} = {value}[/green]"
_KEYCHAIN_NOTE = (
    "[yellow]Not:[/yellow] macOS Keychain izin diyaloğu çıkabilir; Chrome'un çerez anahtarı "
    "için 'İzin ver' seçilmeli."
)

_WEB_SESSION_WARNING = (
    "[yellow]Dikkat:[/yellow] {provider} abonelik oturumunun bu alan adlarındaki çerezleri "
    "ajanın tarayıcısına kopyalanır. Tek yönlüdür; model oturumu değişmez. Profili yükleyen her "
    "ajan çağrısı ayrıca onay ister."
)
_NO_WEB_SESSIONS = "Bu bilgisayarda web model oturumu yok. Önce: fusion web-login chatgpt_web"

ProfileOption = Annotated[str, typer.Option("--profile", "-p", help="Fusion profil adı.")]
DomainOption = Annotated[
    list[str] | None,
    typer.Option(
        "--domain", "-d", help="Yalnız bu alan adları (tekrarlanabilir; onay listesi olur)."
    ),
]
YesOption = Annotated[bool, typer.Option("--yes", "-y", help="Onay sorma (betikler).")]
ChromeDirOption = Annotated[
    Path | None,
    typer.Option("--chrome-dir", help="Chrome kullanıcı veri kökü (varsayılan: sistem)."),
]


def _run(action: object) -> None:
    """Beklenen hataları tek sınırda Türkçe göster; iz basma."""
    try:
        action()  # type: ignore[operator]
    except FusionError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from None


def _domains(values: list[str] | None) -> tuple[str, ...] | None:
    cleaned = tuple(sorted({item.strip().lower() for item in values or () if item.strip()}))
    return cleaned or None


def _confirm(preview: ImportPreview, name: str, yes: bool) -> None:
    # Chrome önizlemesi çözmeden okunur: elde yalnız alan adı sayısı vardır, çerez sayısı yok.
    sayi = (
        f"{preview.cookie_count} çerez, {len(preview.domains)} alan adı"
        if preview.source == SOURCE_FILE
        else f"{len(preview.domains)} alan adı"
    )
    table = Table(title=f"Aktarılacak alan adları ({sayi})")
    table.add_column("Alan adı")
    for domain in preview.domains:
        table.add_row(domain)
    console.print(table)
    if yes:
        return
    if not sys.stdin.isatty():
        console.print(f"[red]{_NEED_YES}[/red]")
        raise typer.Exit(code=1)
    if not typer.confirm(_CONFIRM.format(name=name), default=False):
        console.print(_ABORTED)
        raise typer.Exit(code=1)


def _print_saved(summary: BrowserProfileSummary) -> None:
    console.print(
        _SAVED.format(name=summary.name, count=summary.cookie_count, domains=len(summary.domains))
    )


def _store() -> BrowserProfileStore:
    return default_browser_profile_store()


@app.command("profiles")
def profiles() -> None:
    """Kayıtlı profilleri listele (ad, alan adları, çerez sayısı, kaynak)."""

    def action() -> None:
        rows = _store().list()
        if not rows:
            console.print(_NO_PROFILES)
            return
        table = Table(title="Tarayıcı profilleri")
        for column in ("Ad", "Alan adları", "Çerez", "Kaynak", "Onaylı alan adları"):
            table.add_column(column)
        for item in rows:
            table.add_row(
                item.name,
                ", ".join(item.domains),
                str(item.cookie_count),
                item.source,
                ", ".join(item.allowed_domains) or "hepsi",
            )
        console.print(table)

    _run(action)


@app.command("import-cookies")
def import_cookies(
    path: Annotated[Path, typer.Argument(help="cookies.txt (Netscape) ya da JSON dışa aktarma.")],
    profile: ProfileOption,
    domain: DomainOption = None,
    yes: YesOption = False,
) -> None:
    """Çerez dosyasını bir profile şifreli aktar."""

    def action() -> None:
        domains = _domains(domain)
        preview = preview_cookie_file(path)
        if domains:
            preview = ImportPreview(
                tuple(
                    d
                    for d in preview.domains
                    if any(d == a or d.endswith("." + a) for a in domains)
                ),
                preview.cookie_count,
                preview.source,
            )
        _confirm(preview, profile, yes)
        _print_saved(import_cookie_file(_store(), path, profile, domains=domains))

    _run(action)


@app.command("chrome-profiles")
def chrome_profiles(chrome_dir: ChromeDirOption = None) -> None:
    """Bu bilgisayardaki Chrome profillerini listele (çerez okunmaz)."""

    def action() -> None:
        found = list_chrome_profiles(chrome_dir)
        if not found:
            console.print("Chrome profili bulunamadı.")
            return
        table = Table(title="Chrome profilleri")
        table.add_column("Dizin")
        table.add_column("Ad")
        for item in found:
            table.add_row(item.directory.name, item.label)
        console.print(table)

    _run(action)


@app.command("import-chrome")
def import_chrome(
    profile: ProfileOption,
    chrome_profile: Annotated[
        str, typer.Option("--chrome-profile", help="Chrome profili (dizin ya da görünen ad).")
    ] = "Default",
    domain: DomainOption = None,
    yes: YesOption = False,
    chrome_dir: ChromeDirOption = None,
    all_domains: Annotated[
        bool, typer.Option("--all-domains", help="Alan adı süzgeci olmadan TÜM çerezleri aktar.")
    ] = False,
) -> None:
    """Chrome profilindeki çerezleri (onayla, Keychain izniyle) bir Fusion profiline aktar."""

    def action() -> None:
        domains = _domains(domain)
        if domains is None and not all_domains:
            # Ölçüldü (31 Ekim): `-d` verilmeyince bankalar, e-posta dahil tüm Chrome
            # oturumu ajan tarayıcısına taşınıyordu; onay listesi fiilen 'hepsi' oluyordu.
            console.print(f"[red]{_CHROME_NEED_DOMAIN}[/red]")
            raise typer.Exit(code=1)
        source = find_chrome_profile(chrome_profile, chrome_dir)
        preview = preview_chrome_profile(source)
        if domains:
            preview = ImportPreview(
                tuple(
                    d
                    for d in preview.domains
                    if any(d == a or d.endswith("." + a) for a in domains)
                ),
                preview.cookie_count,
                preview.source,
            )
        _confirm(preview, profile, yes)
        if sys.platform == "darwin":
            console.print(_KEYCHAIN_NOTE)
        _print_saved(import_chrome_profile(_store(), source, profile, domains=domains))

    _run(action)


@app.command("web-sessions")
def web_sessions() -> None:
    """Bu bilgisayardaki web MODEL oturumlarını listele (çerez okunmaz)."""

    def action() -> None:
        found = available_web_sessions()
        if not found:
            console.print(_NO_WEB_SESSIONS)
            return
        table = Table(title="Web model oturumları")
        table.add_column("Sağlayıcı")
        table.add_column("Hesap")
        for item in found:
            table.add_row(item.provider, item.account)
        console.print(table)

    _run(action)


@app.command("import-web-session")
def import_web_session_command(
    provider: Annotated[
        str, typer.Argument(help="Web sağlayıcısı: chatgpt, claude, gemini, copilot.")
    ],
    profile: ProfileOption,
    domain: DomainOption = None,
    account: Annotated[str, typer.Option("--account", help="Web oturumu hesabı.")] = "main",
    yes: YesOption = False,
) -> None:
    """Web model oturumunun seçilen alan adlarını bir Fusion profiline TEK YÖNLÜ kopyala."""

    def action() -> None:
        domains = validate_domains(_domains(domain))
        source = find_web_session(provider, account)
        preview = preview_web_session(source, domains)
        console.print(_WEB_SESSION_WARNING.format(provider=source.provider))
        _confirm(ImportPreview(preview.matching or domains, 0, source.provider), profile, yes)
        _print_saved(asyncio.run(import_web_session(_store(), source, profile, domains)))

    _run(action)


@app.command("login")
def login(
    profile: Annotated[str, typer.Argument(help="Profil adı (yoksa oluşturulur).")],
    url: Annotated[str, typer.Option("--url", help="Açılacak giriş sayfası.")],
) -> None:
    """Görünür pencerede siteye gir; pencereyi kapatınca oturum profile yazılır."""

    def action() -> None:
        from ..providers.profile_login import open_profile_login

        summary = asyncio.run(open_profile_login(_store(), profile, url))
        console.print(_LOGIN_DONE.format(name=summary.name, count=summary.cookie_count))

    _run(action)


@app.command("delete")
def delete(
    profile: Annotated[str, typer.Argument(help="Silinecek profil adı.")],
    yes: YesOption = False,
) -> None:
    """Profili ve şifreli çerezlerini sil."""

    def action() -> None:
        # İçe aktarmayla aynı kural: TTY yokken `--yes` zorunlu. Ölçüldü (31 Ekim): betikte
        # `fusion browser delete is` onaysız siliyordu; geri dönüşü yok.
        if not yes:
            if not sys.stdin.isatty():
                console.print(f"[red]{_NEED_YES}[/red]")
                raise typer.Exit(code=1)
            if not typer.confirm(f"'{profile}' silinsin mi?", default=False):
                console.print(_ABORTED)
                raise typer.Exit(code=1)
        if _store().delete(profile):
            console.print(_DELETED.format(name=profile))
        else:
            console.print(f"[red]{_NOT_FOUND.format(name=profile)}[/red]")
            raise typer.Exit(code=1)

    _run(action)


@app.command("default")
def default(
    profile: Annotated[str, typer.Argument(help="Varsayılan profil adı; boş: kaldır.")] = "",
) -> None:
    """`browser_open` çağrılarında kendiliğinden yüklenecek profili ayarla."""

    def action() -> None:
        config = load_config()
        if profile:
            _store().summary(profile)  # yoksa anlaşılır hata
        write_browser_setting(config, "default_profile", profile)
        console.print(_DEFAULT_SET.format(name=profile) if profile else _DEFAULT_CLEARED)

    _run(action)


@app.command("set")
def set_setting(
    key: Annotated[
        str,
        typer.Argument(
            help="Ayar: headless (pencere görünmez), profiles_enabled ya da panel_agent "
            "(masaüstünde ajan Tarayıcı panelini kullanır)."
        ),
    ],
    value: Annotated[str, typer.Argument(help="on/off (true/false, 1/0 da olur).")],
) -> None:
    """`browser.headless` / `profiles_enabled` / `panel_agent` ayarını yaz."""

    def action() -> None:
        clean = key.strip().lower().replace("-", "_")
        if clean not in ("headless", "profiles_enabled", "panel_agent"):
            console.print(
                "[red]Bilinmeyen ayar. Seçenekler: headless, profiles_enabled, panel_agent "
                "(varsayılan profil için: fusion browser default).[/red]"
            )
            raise typer.Exit(code=1)
        flag = _parse_flag(value)
        write_browser_setting(load_config(), clean, flag)
        console.print(_SETTING_WRITTEN.format(key=clean, value=str(flag).lower()))

    _run(action)


def _parse_flag(raw: str) -> bool:
    lowered = raw.strip().lower()
    if lowered in ("on", "true", "1", "evet", "acik", "açık"):
        return True
    if lowered in ("off", "false", "0", "hayir", "hayır", "kapali", "kapalı"):
        return False
    console.print(f"[red]Değer on ya da off olmalı: {raw}[/red]")
    raise typer.Exit(code=1)
