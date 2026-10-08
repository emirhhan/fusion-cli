"""Kitin mevcut Full HD formatında değişmez host giriş kaynağı."""

from __future__ import annotations

from pathlib import Path

from ..core.remotion_contract import KitScenePlan

BOOTSTRAP_ENTRY = "src/index.tsx"
EDITABLE_COMPOSITION = "src/Composition.tsx"
# Paket video becerisinin mevcut 1920×1080/30 formatı; model ayarı değildir.
VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS = 1920, 1080, 30


def bootstrap_source(composition: str, scenes: tuple[KitScenePlan, ...]) -> bytes:
    duration = sum(scene.duration for scene in scenes)
    return (
        'import React from "react";\n'
        'import {Composition, registerRoot} from "remotion";\n'
        'import {Video} from "./Composition";\n'
        f'const Root = () => <Composition id="{composition}" component={{Video}} '
        f"durationInFrames={{{duration}}} fps={{{VIDEO_FPS}}} "
        f"width={{{VIDEO_WIDTH}}} height={{{VIDEO_HEIGHT}}}/>;\n"
        "registerRoot(Root);\n"
    ).encode()


def editable_source() -> bytes:
    # İçerik bilinmeden sahte başarı üretilmez; model bu bileşeni doldurur.
    return b"export const Video = () => null;\n"


def check_bootstrap_shadow(root: Path) -> None:
    for name in ("index", "Composition"):
        for suffix in (".ts", ".js", ".jsx"):
            if (root / "src" / f"{name}{suffix}").exists():
                raise ValueError("Host girişini/bileşenini gölgeleyen mevcut modül var.")
