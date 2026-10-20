"""Web alanı — sayfa gerçekten yükleniyor ve konsolda hata yok.

İşaret kökteki `index.html`'dir. `package.json` tek başına web kanıtı DEĞİLDİR:
CLI araçları, kütüphaneler ve sunucular da onu taşır.
"""

from __future__ import annotations

from .contract import DomainAdapter


def web_adapter() -> DomainAdapter:
    """Web kanıt sözleşmesi."""
    return DomainAdapter(
        name="web",
        marker="index.html",
        criteria=(
            "sayfa tarayıcıda hatasız yükleniyor",
            "konsolda hata yok",
            "kritik kullanıcı akışı tıklanabiliyor",
        ),
        task_markers=("html", "web sayfası", "web sitesi", "website", "landing page"),
    )
