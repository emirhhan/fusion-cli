# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller `onedir` tarifi: bağımsız Fusion çalışma zamanını derler.

Bu dosya `python -m PyInstaller --clean --noconfirm
desktop_build/runtime/fusion_runtime.spec` ile depo kökünden çalıştırılır.
`onefile` yerine `onedir` kullanılır: `onefile` her açılışta kendini geçici
dizine açar (başlangıç gecikir, bütünlük doğrulaması imkânsızlaşır); `onedir`
bir kez kurulur ve SHA-256 manifestiyle doğrulanır.
"""

import os

from PyInstaller.utils.hooks import collect_all, copy_metadata

# PyInstaller göreli betik/pathex girdilerini SPECPATH'e (bu dosyanın kendi
# dizinine) göre çözer — çalıştırma dizinine göre DEĞİL. Depo kökü bu yüzden
# SPECPATH'ten iki seviye yukarı çıkılarak hesaplanır; böylece tarif hangi
# dizinden tetiklenirse tetiklensin aynı sonucu üretir.
_repo_root = os.path.dirname(os.path.dirname(SPECPATH))  # noqa: F821

datas = []
binaries = []
hiddenimports = []
# `tiktoken_ext` bir namespace plugin paketidir. PyInstaller yalnız `tiktoken`
# modülünü görürse cl100k_base gibi gerçek encoding kayıtları pakete girmez ve
# LiteLLM ilk uzun görevde "Plugins found: []" ile çöker.
for package in (
    "fusion_cli",
    "litellm",
    "tiktoken",
    "tiktoken_ext",
    "chromadb",
    "keyring",
    "httpx",
    "mcp",
    "piper",
    "onnxruntime",
    # Web sağlayıcıları (ChatGPT/Claude/Gemini arayüzü) Playwright'a bağlıdır.
    # Ölçüldü (alpha.12 release'i): paket toplanmadığı için paketlenmiş uygulamada
    # HİÇBİR web sağlayıcısı çalışmıyordu; arayüzde duruyorlar ama altlarında motor
    # yoktu ve kullanıcı "Playwright kurulu değil" hatasını alıyordu. Tarayıcı
    # İKİLİLERİ ayrı bir mesele: onlar `~/Library/Caches/ms-playwright` altında
    # yaşar ve `playwright install chromium` ile gelir; pakete girmezler.
    "playwright",
):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden
for distribution in (
    "fusion-cli",
    "litellm",
    "chromadb",
    "keyring",
    "httpx",
    "piper-tts",
    "onnxruntime",
    "playwright",
):
    datas += copy_metadata(distribution)

a = Analysis(
    [os.path.join(SPECPATH, "entrypoint.py")],  # noqa: F821
    pathex=[os.path.join(_repo_root, "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="fusion", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="fusion-runtime")
