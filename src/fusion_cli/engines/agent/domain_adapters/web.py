"""Web alanı — planlayıcıya verilen kabul koşulları.

Bu adaptör kapı komutu ya da çıktı işareti TANIMLAMAZ; yalnız planlayıcıya "bitti"nin ne
demek olduğunu söyler. Sayfanın gerçekten yüklendiğini ve konsolda hata olmadığını ÖLÇEN
şey `engines/agent/browser_verify.py::BrowserVerifier`'dır (`build_verifier` ekler);
docstring eskiden bu ölçümü adaptöre atfediyordu (E1-11).

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
