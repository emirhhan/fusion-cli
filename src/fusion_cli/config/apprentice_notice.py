"""Bir sonraki açılışta gösterilecek TEK SEFERLİK "ücretsiz çırağa dön" bildirimi.

Kullanıcı `/development` ile bir web modeline (`chatgpt_web/…`, `tags: [strict]`)
kilitlenmiş olabilir; bu geçmişte bilerek yapılmış, geri dönüşü olmayan bir
seçimdir (Faz 3 denetim bulguları C5/C9). Bunu SESSİZCE değiştirmek yerine bir
sonraki açılışta tek seferlik bir bildirim gösterilir; kullanıcı isterse
`kontrol.cirak_varsayilanina_don` / `/level cirak` ile döner, istemezse bildirim
bir daha çıkmaz.

İşaret NEREYE konur: `config.yaml`'a DEĞİL. O dosya `config/writer.py`'nin dar ve
tek amaçlı bir sözleşmeyle yönettiği tek kaynaktır (`MODEL_SECTIONS`); "gösterildi
mi" gibi UI durumu oraya YENİ bir anahtar olarak eklemek RULES "Yapılandırma"
ilkesini ("aynı içeriğin ikinci bir kopyası tutulmaz", "yalnızca tek kaynaktan
yönetilir") ters yönden çiğner — writer'ın yazdığı alan kümesi büyür ve model
seçimiyle ilgisiz bir kaygıyla karışır. Bunun yerine kullanıcı yapılandırma
dizininin YANINDA, yalnızca bu tek boole durumu taşıyan ayrı ve dar bir işaret
dosyası tutulur.
"""

from __future__ import annotations

from pathlib import Path

from .paths import user_config_dir

#: İşaret dosyasının adı. İçeriği önemsizdir; yalnızca VARLIĞI okunur.
_MARKER_NAME = ".cirak_bildirimi_gosterildi"


def _marker_path(directory: Path | None) -> Path:
    return (directory or user_config_dir()) / _MARKER_NAME


def apprentice_notice_shown(directory: Path | None = None) -> bool:
    """Bildirim daha önce gösterildi mi? `directory` verilmezse kullanıcı yapılandırma dizini."""
    return _marker_path(directory).is_file()


def mark_apprentice_notice_shown(directory: Path | None = None) -> None:
    """Bildirimin gösterildiğini kalıcı olarak işaretle; bir daha çıkmaz."""
    path = _marker_path(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
