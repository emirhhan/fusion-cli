"""Plan kipinde sınıflandırıcıya giden kabuk komutunun kaynağı düzenleyip düzenlemediği (#318).

Claude Code plan kipinde salt okunur olmayan komutu otomatik kip sınıflandırıcısına verir;
o sınıflandırıcı plan kipini bilen bir modeldir ve plan "kaynağı düzenlemez" (permission-modes).
Fusion'ın otomatik kip denetçisi ise kipten habersiz bir sezgidir (`auto_risk`): `echo x > a.py`
ya da `rm -rf build` onda risksizdir. Plan kipinin düzenleme yasağı gevşemesin diye dosya
yazan/silen/taşıyan komut sınıflandırıcıda REDDEDİLİR; kurulum/derleme/test serbesttir.
"""

from __future__ import annotations

from ...tools.auto_policy import command_words, written_files

#: Doğrudan dosya sistemi düzenleyen komutlar (plan kipinde sınıflandırıcı reddeder).
_EDITING_COMMANDS = frozenset(
    {
        "rm", "rmdir", "mv", "cp", "touch", "mkdir", "ln", "chmod", "chown", "truncate",
        "dd", "install", "rsync", "patch", "unzip", "tar", "trash", "shred",
    }
)  # fmt: skip
#: Çalışma ağacını değiştiren git alt komutları.
_EDITING_GIT = frozenset(
    {"add", "commit", "checkout", "switch", "reset", "restore", "merge", "rebase", "stash",
     "apply", "am", "cherry-pick", "revert", "rm", "mv", "clean", "pull", "push", "tag"}
)  # fmt: skip


def edits_source(command: str) -> bool:
    """Komut dosya yazıyor, siliyor, taşıyor ya da git çalışma ağacını değiştiriyor mu?"""
    if any(target != "/dev/null" for target in written_files(command)):
        return True
    for parts in command_words(command):
        name = parts[0].rsplit("/", 1)[-1]
        if name in _EDITING_COMMANDS:
            return True
        if name == "git" and any(part in _EDITING_GIT for part in parts[1:3]):
            return True
        if name in {"sed", "perl"} and any(part.startswith("-i") for part in parts[1:]):
            return True
    return False
