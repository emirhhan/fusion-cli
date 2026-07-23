"""`fusion setup` — ilk kurulum.

Global kurulumdan (pipx/pip) sonra bir kez çalıştırılır: kullanıcı yapılandırma
dizinine `config.yaml` ve `.env` şablonu bırakır, sonra anahtar alınacak adresleri
gösterir.

Var olan dosyaların ÜZERİNE YAZMAZ. Kurulum sihirbazının kullanıcının anahtarlarını
silmesi kabul edilemez; mevcut dosya varsa yalnızca bildirilir.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from ..config.paths import bundled_defaults, memory_dir, user_config_dir
from ..ui import messages, theme

ENV_TEMPLATE = """# Fusion-CLI API anahtarları — en az birini doldur.

# NVIDIA NIM (ücretsiz geliştirici anahtarı): https://build.nvidia.com/
NVIDIA_NIM_API_KEY=
# Boş bırakılırsa NVIDIA'nın barındırdığı uç kullanılır.
NVIDIA_NIM_API_BASE=

# OpenRouter (ücretsiz katman): https://openrouter.ai/keys
OPENROUTER_API_KEY=

# Langfuse izleme (opsiyonel — boş bırakılırsa sessizce kapalı)
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=
"""

#: Kullanıcı config'inde başlangıç olarak bırakılan açıklamalı şablon.
CONFIG_TEMPLATE = """# Fusion-CLI kullanıcı yapılandırması.
#
# Buraya YALNIZCA değiştirmek istediğin anahtarları yaz: bu dosya pakete gömülü
# varsayılanların ÜZERİNE derin birleştirilir, onların yerini almaz.
#
# Tüm varsayılanları görmek için:  fusion config show
# Kullanılabilir modelleri görmek için:  fusion models --fetch

# Örnek — daha uzun cevaplar:
# runtime:
#   max_tokens: 4096

# Örnek — agent modelini değiştir:
# agent:
#   name: kendi-modelim
#   model: openrouter/bir/model:free

# Örnek — havuza aday EKLE (mevcutları değiştirmeden):
# extra_candidates:
#   - name: yerel-qwen
#     model: ollama/qwen2.5-coder:7b
#     tags: [code]
"""


def run_setup(console: Console) -> None:
    """Yapılandırma ve .env şablonlarını oluştur, sırada ne olduğunu söyle."""
    directory = user_config_dir()
    directory.mkdir(parents=True, exist_ok=True)

    _create(console, directory / "config.yaml", CONFIG_TEMPLATE)
    _create(console, directory / ".env", ENV_TEMPLATE)

    console.print()
    console.print(f"[bold]{messages.SETUP_NEXT_STEPS}[/bold]")
    console.print(f"  1. {messages.SETUP_STEP_KEYS.format(path=directory / '.env')}")
    console.print(f"     [{theme.DIM}]NVIDIA NIM  https://build.nvidia.com/[/{theme.DIM}]")
    console.print(f"     [{theme.DIM}]OpenRouter  https://openrouter.ai/keys[/{theme.DIM}]")
    console.print(f"  2. {messages.SETUP_STEP_RUN}")
    console.print()
    console.print(f"[{theme.DIM}]{messages.SETUP_PATHS}[/{theme.DIM}]")
    console.print(f"[{theme.DIM}]  yapılandırma: {directory}[/{theme.DIM}]")
    console.print(f"[{theme.DIM}]  bellek:       {memory_dir()}[/{theme.DIM}]")
    console.print(f"[{theme.DIM}]  varsayılanlar:{bundled_defaults()}[/{theme.DIM}]")


def _create(console: Console, path: Path, content: str) -> None:
    if path.exists():
        console.print(f"[{theme.DIM}]{messages.SETUP_EXISTS.format(path=path)}[/{theme.DIM}]")
        return
    path.write_text(content, encoding="utf-8")
    console.print(
        f"[{theme.OK}]{theme.ICON_OK}[/{theme.OK}] {messages.SETUP_CREATED.format(path=path)}"
    )
