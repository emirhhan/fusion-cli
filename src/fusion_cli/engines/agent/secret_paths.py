"""Üçüncü tarafa (web öğretmeni) gitmemesi gereken dosya adları ve konumları.

Öğretmen ChatGPT/Gemini web oturumudur: oraya giden her bayt kullanıcının makinesini
terk eder. `redact()` yalnız anahtar BİÇİMLİ değerleri maskeler; `id_rsa`, `*.pem`,
`credentials.json`, `secrets.enc`, `terraform.tfstate` gibi dosyaların içeriği bu
desenlere uymayabilir. Bu yüzden karar dosya ADINA ve konumuna göre, içerik okunmadan
verilir.

`tools/search.py` benzer bir listeyi arama çıktısı için tutar; orada `config.json` ve
`settings.*` da sır sayılır (arama için makul). Öğretmen kesitinde bu fazla geniştir:
kodun kendisi olan yapılandırma dosyaları öğretmenin görmesi gereken şeydir.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Tam ad eşleşmesi (küçük harfe çevrilmiş).
_SECRET_NAMES = frozenset(
    {
        ".npmrc",
        ".netrc",
        ".git-credentials",
        ".pypirc",
        ".pgpass",
        ".htpasswd",
        ".dockercfg",
        "id_rsa",
        "id_dsa",
        "id_ed25519",
        "id_ecdsa",
        "service-account.json",
        "kubeconfig",
        "secrets.enc",
        "master.key",
    }
)
#: Ad parçası olarak geçen sır sözcükleri (`credentials.json`, `my-secret.yaml`…).
_SECRET_STEM = re.compile(
    r"(?:^|[._-])(credential|credentials|secret|secrets|token|tokens|private|passwd|password)"
    r"(?:$|[._-])",
    re.IGNORECASE,
)
#: Sır sözcüğü yalnız VERİ dosyalarında alarm sayılır: `token.py`, `reset-password.tsx`
#: kaynak koddur ve öğretmenin görmesi gereken şeydir; `credentials.json` veridir.
_DATA_SUFFIXES = frozenset(
    {"", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".txt", ".enc", ".xml"}
    | {".properties", ".env", ".csv", ".db", ".sqlite", ".bak"}
)
_SECRET_SUFFIXES = frozenset(
    {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".gpg", ".asc", ".kdbx", ".tfvars"}
)
#: Bu dizinlerin altındaki her şey sırdır.
_SECRET_DIRS = frozenset({".ssh", ".aws", ".azure", ".gnupg", ".kube", ".docker", ".fusion"})


def is_secret_path(path: Path) -> bool:
    """Dosya ADI ya da konumu bir sır dosyasına işaret ediyor mu? (içerik okunmaz)"""
    name = path.name.casefold()
    if name == ".env" or name.startswith(".env."):
        return True
    if name in _SECRET_NAMES or name.startswith("terraform.tfstate"):
        return True
    if name.startswith("id_") and not name.endswith(".pub"):
        return name.removeprefix("id_").split(".")[0] in {"rsa", "dsa", "ed25519", "ecdsa"}
    if path.suffix.casefold() in _SECRET_SUFFIXES:
        return True
    if path.suffix.casefold() in _DATA_SUFFIXES and _SECRET_STEM.search(path.name):
        return True
    return any(part.casefold() in _SECRET_DIRS for part in path.parts[:-1])
