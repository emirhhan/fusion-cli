"""Tur başında MCP istem çağrısını ve kaynak anmalarını çöz (P-049).

`ensure_mcp_tools` bağlantıları kurduktan SONRA çağrılır (REPL `_drive_agent`,
`cli.session.run_agent_task`); böylece terminal, tam ekran, masaüstü ve tek atış aynı yoldan
geçer. Bkz. `references.py` biçim ve güven kuralları.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from ..config.models import McpServerConfig
from .call_errors import describe_call_error
from .pool import connected_mcp_client, mcp_catalogs
from .references import (
    RESOURCE_MAX_MENTIONS,
    McpExpansion,
    bind_arguments,
    find_prompt,
    parse_prompt_call,
    resource_mentions,
)

PROMPT_NOT_FOUND = (
    "MCP istemi bulunamadı: /{name}. `/mcp prompts` ile listele; sunucu yeni bağlandıysa "
    "listeyi görmek için bir tur bekle."
)
PROMPT_NOT_CONNECTED = "MCP sunucusu bağlı değil: {server}. `/mcp reconnect {server}` dene."
PROMPT_BAD_ARGS = "/{name}: {error}. Kullanım: /{name} {usage}"
PROMPT_FAILED = "MCP istemi alınamadı ({server}/{prompt}): {error}"
PROMPT_EMPTY = "MCP istemi boş döndü ({server}/{prompt}); tur çalıştırılmadı."
PROMPT_LOADED = "MCP istemi yüklendi: {server}/{prompt}"
RESOURCE_LOADED = "MCP kaynağı bağlama eklendi: @{server}:{uri}"
RESOURCE_NOT_CONNECTED = "@{server}:{uri}: sunucu bağlı değil, kaynak eklenmedi"
RESOURCE_FAILED = "@{server}:{uri}: okunamadı ({error})"
RESOURCE_TOO_MANY = "En fazla {limit} MCP kaynağı eklenir; fazlası atlandı."


async def expand_mcp_references(task: str, configs: Sequence[McpServerConfig]) -> McpExpansion:
    """`/mcp__s__p argümanlar` → istem metni; `@s:uri` → bağlam bloğu. Başvuru yoksa aynen."""
    expansion = await _expand_references(task, configs)
    instructions = server_instructions_block(configs)
    if not instructions:
        return expansion
    context = "\n\n".join(part for part in (instructions, expansion.context) if part)
    return replace(expansion, context=context)


#: Claude Code'un sistem bağlamına koyduğu başlık (#263).
INSTRUCTIONS_HEADER = (
    "# MCP Server Instructions\n\nThe following MCP servers have provided instructions "
    "for how to use their tools and resources:"
)


def server_instructions_block(configs: Sequence[McpServerConfig]) -> str:
    """Bağlı sunucuların `initialize` talimatları (Claude Code biçimi); yoksa boş."""
    sections: list[str] = []
    for config in configs:
        try:
            client = connected_mcp_client(config.name)
        except AttributeError:  # havuz henüz kurulmadı (sahte/yarım ortam)
            client = None
        reader = getattr(client, "server_instructions", None)
        text = reader(config.name) if callable(reader) else ""
        if text:
            sections.append(f"## {config.name}\n{text}")
    return "\n\n".join((INSTRUCTIONS_HEADER, *sections)) if sections else ""


async def _expand_references(task: str, configs: Sequence[McpServerConfig]) -> McpExpansion:
    call = parse_prompt_call(task)
    mentions = resource_mentions(task, [config.name for config in configs])
    if call is None and not mentions:
        return McpExpansion(task)
    notes: list[str] = []
    new_task = task
    if call is not None:
        name, raw = call
        # Kaynak anmaları istem argümanı değildir; bağlama ayrıca girer.
        for server, uri in mentions:
            raw = raw.replace(f"@{server}:{uri}", " ")
        resolved = await _resolve_prompt(name, " ".join(raw.split()))
        if resolved.error:
            return resolved
        new_task = resolved.task
        notes.extend(resolved.notes)
    blocks: list[str] = []
    loaded: list[str] = []
    warnings: list[str] = []
    for server, uri in mentions[:RESOURCE_MAX_MENTIONS]:
        client = connected_mcp_client(server)
        if client is None:
            warnings.append(RESOURCE_NOT_CONNECTED.format(server=server, uri=uri))
            continue
        try:
            blocks.append(await client.read_resource(server, uri))
        except Exception as error:  # tek kaynak turu düşürmez; kullanıcıya not
            warnings.append(
                RESOURCE_FAILED.format(server=server, uri=uri, error=describe_call_error(error))
            )
            continue
        loaded.append(f"{server}:{uri}")
        notes.append(RESOURCE_LOADED.format(server=server, uri=uri))
    if len(mentions) > RESOURCE_MAX_MENTIONS:
        warnings.append(RESOURCE_TOO_MANY.format(limit=RESOURCE_MAX_MENTIONS))
    return McpExpansion(
        new_task,
        "\n\n".join(blocks),
        tuple(notes),
        resources=tuple(loaded),
        warnings=tuple(warnings),
    )


async def _resolve_prompt(name: str, raw: str) -> McpExpansion:
    prompts = [item for catalog in mcp_catalogs().values() for item in catalog.prompts]
    prompt = find_prompt(prompts, name)
    if prompt is None:
        return McpExpansion("", error=PROMPT_NOT_FOUND.format(name=name))
    client = connected_mcp_client(prompt.server)
    if client is None:
        return McpExpansion("", error=PROMPT_NOT_CONNECTED.format(server=prompt.server))
    arguments, problem = bind_arguments(prompt, raw)
    if problem:
        return McpExpansion(
            "", error=PROMPT_BAD_ARGS.format(name=name, error=problem, usage=prompt.usage)
        )
    try:
        text = await client.get_prompt(prompt.server, prompt.name, arguments)
    except Exception as error:  # sunucu hatası kullanıcıya eyleme dönük metinle döner
        return McpExpansion(
            "",
            error=PROMPT_FAILED.format(
                server=prompt.server, prompt=prompt.name, error=describe_call_error(error)
            ),
        )
    if not text.strip():
        return McpExpansion("", error=PROMPT_EMPTY.format(server=prompt.server, prompt=prompt.name))
    return McpExpansion(
        text, notes=(PROMPT_LOADED.format(server=prompt.server, prompt=prompt.name),)
    )
