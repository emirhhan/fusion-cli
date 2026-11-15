"""Eklenti yazarlığı: `fusion plugin init|new`, `tag`, `test` (Claude Code, #380, #401)."""

from __future__ import annotations

from pathlib import Path

import typer

from ..core.plugins import PluginError
from ..tools.plugin_scaffold import scaffold_plugin
from ..tools.plugin_tag import create_tag, plan_tag
from .plugin_commands import app

CREATED = 'Eklenti oluşturuldu: "{name}" → ~/.claude/skills/{name}'
CREATED_HINT = (
    "  Sonraki oturumda {name}@skills-dir olarak kendiliğinden yüklenir; şimdi yüklemek için "
    "/reload-plugins.\n  Kapat: fusion plugin disable {name}@skills-dir. Kaldır: klasörü sil."
)
TAG_HEADER = "Plugin:  {name}\nVersion: {version} (plugin.json'dan)\nTag:     {tag}\n"
TAG_DRY = "Deneme — {tag} etiketi HEAD'e konacaktı: {repo}\n  {tag_command}\n  {push_command}"
TAG_CREATED = "Etiket oluşturuldu: {tag}"
TAG_PUSHED = "Etiket gönderildi: {remote}"
TAG_PUSH_HINT = "  Göndermek için: {push_command}"
TEST_UNSUPPORTED = (
    "plugin test Claude Code modlarının *.test.ts dosyalarını 'claude-code/testing' kitiyle "
    "koşar; Fusion'da mod sistemi ve bu kit yok. Eklenti doğrulaması için: fusion plugin validate"
)


def _fail(error: PluginError) -> typer.Exit:
    typer.echo(f"✘ {error}", err=True)
    return typer.Exit(1)


@app.command("init", context_settings={"allow_extra_args": True, "ignore_unknown_options": False})
def init(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Eklenti adı (kebab-case önerilir)"),
    author: str | None = typer.Option(None, "--author", help="Yazar (varsayılan git user.name)"),
    author_email: str | None = typer.Option(
        None, "--author-email", help="E-posta (varsayılan git user.email)"
    ),
    description: str = typer.Option("", "--description", help="Bildirim açıklaması"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Var olan .claude-plugin/'in üstüne yaz"
    ),
    with_components: list[str] = typer.Option(  # noqa: B008
        [],
        "--with",
        help="Ek iskelet: skills, agents, hooks, mcp, lsp, output-style, channel",
    ),
) -> None:
    """~/.claude/skills/<ad>/ altına eklenti iskeleti kur (<ad>@skills-dir olarak yüklenir)."""
    # Claude `--with skills hooks` (değişken sayıda): `--with` sonrası çıplak sözcükler de alınır.
    extra = list(ctx.args) if with_components else []
    chosen = [
        p.strip() for item in (*with_components, *extra) for p in item.split(",") if p.strip()
    ]
    try:
        made = scaffold_plugin(
            name,
            author=author,
            email=author_email,
            description=description,
            force=force,
            with_components=chosen,
        )
    except PluginError as error:
        raise _fail(error) from error
    if made.warnings:
        typer.echo(f"⚠ {len(made.warnings)} uyarı:")
        typer.echo("\n".join(f"  ❯ {warning}" for warning in made.warnings) + "\n")
    typer.echo("✔ " + CREATED.format(name=made.name))
    typer.echo(CREATED_HINT.format(name=made.name))


app.command(
    "new",
    hidden=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": False},
)(init)


@app.command("tag")
def tag(
    path: str = typer.Argument(".", help="Eklenti klasörü (varsayılan: bulunulan klasör)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Etiketlemeden ne yapılacağını bas"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Kirli çalışma ağacı ve var olan etiket denetimini atla"
    ),
    message: str = typer.Option("", "--message", "-m", help="Etiket açıklaması (%s = sürüm)"),
    push: bool = typer.Option(False, "--push", help="Oluşturduktan sonra --remote'a gönder"),
    remote: str = typer.Option("origin", "--remote", help="--push uzak deposu"),
) -> None:
    """Eklenti sürümü için <ad>--v<sürüm> git etiketi (plugin.json ve pazar girdisi uyuşmalı)."""
    try:
        plan = plan_tag(Path(path), message=message, remote=remote, force=force)
    except PluginError as error:
        raise _fail(error) from error
    typer.echo(TAG_HEADER.format(name=plan.name, version=plan.version, tag=plan.tag))
    if dry_run:
        typer.echo(
            "✔ "
            + TAG_DRY.format(
                tag=plan.tag,
                repo=plan.repo,
                tag_command=plan.tag_command,
                push_command=plan.push_command,
            )
        )
        return
    try:
        create_tag(plan, force=force, push=push)
    except PluginError as error:
        raise _fail(error) from error
    typer.echo("✔ " + TAG_CREATED.format(tag=plan.tag))
    if push:
        typer.echo("✔ " + TAG_PUSHED.format(remote=plan.remote))
    else:
        typer.echo(TAG_PUSH_HINT.format(push_command=plan.push_command))


@app.command("test")
def test(dir: str = typer.Argument(".", help="Modun klasörü")) -> None:
    """Bir modun testlerini koş (Claude Code modları; Fusion'da yok)."""
    del dir
    typer.echo(TEST_UNSUPPORTED, err=True)
    raise typer.Exit(1)
