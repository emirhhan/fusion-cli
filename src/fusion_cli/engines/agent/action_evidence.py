"""İşin devamını ve modelin işlem beyanını gerçek tur kanıtına bağla.

İstek sınıflandırıcısı bir ifadeyi tanımasa da modelin değiştirme/çalıştırma
beyanı kanıtsız teslim edilemez. Geçmiş yalnız açık devam talebinde kullanılır;
yeni bir soru eski işin değişiklik zorunluluğunu miras almaz.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from ...core.types import Message
from ..effects.detect import required_effect_for

_CONTINUATION = re.compile(
    r"(?:tamam(?:dır)?[ ,]*)?(?:kaldığın yerden |kaldigin yerden )?devam et"
    r"(?: lütfen)?[.!\s]*|(?:please )?continue(?: where you left off)?[.!\s]*"
    r"|resume[.!\s]*",
    re.IGNORECASE,
)
_START_WORK = re.compile(
    r"(?:tamam(?:dır)?[, ]+)?(?:şimdi |simdi )?"
    r"(?:(?:çalışmaya|calismaya|işe|ise) başla|start working)[.!\s]*",
    re.IGNORECASE,
)
# İlk şahıs, devam eden iş ve pasif sonuç beyanları. Emir kipindeki örnek
# komutlar bu desenlere girmez; alıntılar/kod blokları ayrıca çıkarılır.
_MUTATION_CLAIM = re.compile(
    r"\b(?:ekle(?:dim|dik|yeceğim|yecegim|yorum)|düzelt(?:tim|tik|eceğim|iyorum)|"
    r"duzelt(?:tim|tik|ecegim|iyorum)|güncelle(?:dim|dik|yeceğim|yorum)|"
    r"guncelle(?:dim|dik|yecegim|yorum)|oluştur(?:dum|duk|acağım|uyorum)|"
    r"olustur(?:dum|duk|acagim|uyorum)|değiştir(?:dim|dik|eceğim|iyorum)|"
    r"degistir(?:dim|dik|ecegim|iyorum)|kaydet(?:tim|tik|eceğim|iyorum)|"
    r"sil(?:dim|dik|eceğim|iyorum))\b|"
    r"\b(?:dosya\w*|kod\w*|font\w*|katman\w*|ayar\w*|file\w*)\b[^.!?\n]{0,100}"
    r"\b(?:eklendi|düzeltildi|duzeltildi|güncellendi|guncellendi|oluşturuldu|"
    r"olusturuldu|değiştirildi|degistirildi|kaydedildi|silindi)\b|"
    r"\b(?:I|we)(?:'ve| have)?\s+(?:added|created|modified|updated|edited|fixed|saved|deleted)\b|"
    r"\b(?:files?|code|settings?)\b[^.!?\n]{0,60}\b(?:was|were|has been|have been)\s+"
    r"(?:added|created|modified|updated|edited|fixed|saved|deleted)\b",
    re.IGNORECASE,
)
_SHELL_CLAIM = re.compile(
    r"\b(?:çalıştırdım|calistirdim|başlattım|baslattim|kurdum|yükledim|yukledim)\b|"
    r"\b(?:I|we)(?:'ve| have)?\s+(?:ran|executed|installed|restarted|deployed)\b",
    re.IGNORECASE,
)
_EXTERNAL_SCOPE = re.compile(
    r"\b(?:dosya\w*|klasör\w*|klasor\w*|dizin\w*|kod\w*|proje\w*|"
    r"uygulama\w*|fonksiyon\w*|modül\w*|modul\w*|font\w*|katman\w*|"
    r"ayar\w*|yama\w*|yazı tipi|yazi tipi|file\w*|folder\w*|director\w*|"
    r"code|project\w*|app|application\w*|function\w*|module\w*|"
    r"font\w*|layer\w*|setting\w*|patch\w*|repository)\b",
    re.IGNORECASE,
)
_FILE_REFERENCE = re.compile(r"(?:[\w.@~-]+(?:/[\w.@~-]+)+|[\w.@~/-]+\.[A-Za-z][A-Za-z0-9]*)")
_QUOTED = re.compile(r'```.*?```|`[^`]*`|^[ \t]*>[^\n]*|["“][^"”\n]*["”]', re.M | re.S)


def task_effect(task: str, history: Sequence[Message] = ()) -> str | None:
    """Yalnız devam talebinde en son gerçek kullanıcı görevini çözümle."""
    effect = required_effect_for(task)
    if effect is not None:
        return effect
    # Yalnız bağımsız bir emir cümleciği: alıntı, olumsuzluk veya açıklama
    # görevini değiştirme talebine dönüştürme. İşin türü bilinmiyorsa dosya
    # yazmasını zorlama; en azından gerçek bir araç gözlemi gerektir.
    clauses = re.split(r"[;\n]|\b(?:ve|and)\b", _prose(task), flags=re.I)
    if any(_START_WORK.fullmatch(clause.strip()) for clause in clauses):
        return "tool_action"
    if not _CONTINUATION.fullmatch(task.strip()):
        return None
    for message in reversed(history):
        if message.role != "user" or message.harness_note:
            continue
        if _CONTINUATION.fullmatch(message.content.strip()):
            continue
        return task_effect(message.content)
    return None


def claimed_effects(text: str) -> tuple[str, ...]:
    """Alıntı dışındaki olumlu dış işlem beyanlarının gerektirdiği kanıtlar."""
    clauses = re.split(r"(?<=[.!?])\s+|[;\n]", _prose(text))
    prose = [clause for clause in clauses if not _is_qualified(clause)]
    effects = []
    if any(
        _MUTATION_CLAIM.search(clause)
        and (
            _EXTERNAL_SCOPE.search(clause)
            or _FILE_REFERENCE.search(clause)
            or _MUTATION_CLAIM.fullmatch(clause.strip(" .!:"))
        )
        for clause in prose
    ):
        effects.append("workspace_mutation")
    if any(_SHELL_CLAIM.search(clause) for clause in prose):
        effects.append("shell_action")
    return tuple(effects)


def _is_qualified(clause: str) -> bool:
    """Soru, öneri ve geçmiş anlatımı bu turun olumlu işlem beyanı değildir."""
    if clause.rstrip().endswith("?"):
        return True
    # Sohbette teslim edilen kod örneği kendi başına bir dosya işlemi değildir.
    inline_example = re.search(
        r"\b(?:kod örne[ğg]\w*|örnek kod|(?:following|inline) (?:code )?(?:example|snippet))\b",
        clause,
        re.I,
    )
    external_target = re.search(
        r"\b(?:dosya\w*|disk\w*|klasör\w*|file\w*|folder\w*)\b", clause, re.I
    )
    if inline_example and not external_target:
        return True
    if re.search(
        r"^\s*(?:dün|dun|önceki turda|onceki turda|yesterday|in the previous turn)\b",
        clause,
        re.I,
    ):
        return True
    condition = re.search(
        r"\b(?:istersen|isterseniz|onay verirsen|uygun olunca|if you (?:want|approve))\b",
        clause,
        re.I,
    )
    claim = _MUTATION_CLAIM.search(clause) or _SHELL_CLAIM.search(clause)
    # Sondaki "istersen açıklarım" daha önceki "dosyayı değiştirdim" iddiasını
    # silemez; koşul yalnız kendisinden SONRA gelen eylemi nitelendirir.
    return condition is not None and (claim is None or condition.start() < claim.start())


def _prose(text: str) -> str:
    """Kod/alıntı beyanlarını çıkar; alıntılanmış gerçek dosya hedefini koru."""
    return _QUOTED.sub(_unquote_target, text)


def _unquote_target(match: re.Match[str]) -> str:
    quoted = match.group()
    if quoted.startswith(("`", '"', "“")) and not quoted.startswith("```"):
        target = quoted[1:-1]
        if _FILE_REFERENCE.fullmatch(target):
            return target
    return " "
