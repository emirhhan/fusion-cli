"""Web iskelesi — referansı prompta değil DİSKE koyar.

Neden: tasarım referansı bugüne kadar sistem promptuna enjekte ediliyordu; bu oturumda
üç kez ölçtük ki model prompt kurallarını sıkça görmezden geliyor, araç sonucuna ise
tepki veriyor. Araştırma da aynı yöne işaret etti: bolt.new, v0 ve Lovable sabit bir
iskeleden başlatıyor — model kural OKUMUYOR, var olan dosyayı DOLDURUYOR.
"""

from __future__ import annotations

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import files as file_tools
from fusion_cli.tools.scaffold_tool import SCAFFOLD_FILES, scaffold_web


def test_iskele_dosyalari_yazilir(tmp_path):
    context = ToolContext(root=tmp_path)

    sonuc = scaffold_web({"path": "site"}, context)

    assert sonuc.ok, sonuc.output
    for ad in SCAFFOLD_FILES:
        assert (tmp_path / "site" / ad).is_file(), f"{ad} yazılmadı"


def test_yazilan_dosyalar_dogrulama_kapisina_kayitlanir(tmp_path):
    """Kapı yalnızca dokunulan dosyalara bakar; iskele de oraya girmeli."""
    context = ToolContext(root=tmp_path)

    scaffold_web({"path": "site"}, context)

    assert any(p.name == "tokens.css" for p in context.touched)


def test_var_olan_dosyanin_uzerine_yazilmaz(tmp_path):
    """İskele yıkıcı DEĞİLDİR: kullanıcının dosyasını ezmez."""
    hedef = tmp_path / "site"
    hedef.mkdir()
    (hedef / "tokens.css").write_text("/* benim dosyam */", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    sonuc = scaffold_web({"path": "site"}, context)

    assert (hedef / "tokens.css").read_text(encoding="utf-8") == "/* benim dosyam */"
    assert "atlandı" in sonuc.output.lower() or "korundu" in sonuc.output.lower()


def test_tokens_gercek_degerler_tasiyor(tmp_path):
    context = ToolContext(root=tmp_path)
    scaffold_web({"path": "."}, context)

    css = (tmp_path / "tokens.css").read_text(encoding="utf-8")

    assert "--space-5: 24px" in css
    assert "--radius-md" in css and "--shadow-sm" in css
    assert ".btn--primary" in css, "hazır buton stili olmalı"


def test_format_js_fiyati_bolmez(tmp_path):
    """₺149,99 hatasının kökü: model fiyatı 100'e bölüyordu."""
    context = ToolContext(root=tmp_path)
    scaffold_web({"path": "."}, context)

    js = (tmp_path / "format.js").read_text(encoding="utf-8")

    assert "/ 100" not in js
    assert "formatPrice" in js and "tr-TR" in js


def test_iskelet_html_stilleri_ve_scripti_bagliyor(tmp_path):
    """Üçüncü koşuda düzeltici tur <script> etiketini düşürüp sayfayı boşaltmıştı."""
    context = ToolContext(root=tmp_path)
    scaffold_web({"path": "."}, context)

    html = (tmp_path / "index.html").read_text(encoding="utf-8")

    assert 'href="tokens.css"' in html
    assert "script.js" in html
    assert "<main>" in html and "<footer" in html


def test_iskele_kapinin_yasakladiklarini_icermez(tmp_path):
    """İskele TAMAMLANMAMIŞ bir sayfadır (style.css'i model yazar), ama kapının
    yasakladığı hiçbir şeyi İÇERMEMELİ: ölü görsel servisi, boş bağlantı, eksik <main>.
    """
    from fusion_cli.engines.agent.web_verify import inspect_web_output

    context = ToolContext(root=tmp_path)
    scaffold_web({"path": "."}, context)
    dosyalar = {p.name: p.read_text(encoding="utf-8") for p in tmp_path.iterdir() if p.is_file()}

    bulgular = inspect_web_output(dosyalar)
    yasak = [b for b in bulgular if any(k in b for k in ("boş bağlantı", "<main>", "placeholder"))]

    assert not yasak, yasak


def test_yol_verilmezse_calisma_dizinine_yazar(tmp_path):
    context = ToolContext(root=tmp_path)

    scaffold_web({}, context)

    assert (tmp_path / "tokens.css").is_file()


def test_kok_kisitlamasina_uyar(tmp_path):
    """restrict_to_root açıkken kök dışına yazılamaz."""
    from fusion_cli.core.errors import PathAccessError

    context = ToolContext(root=tmp_path, restrict_to_root=True)

    try:
        scaffold_web({"path": "../disari"}, context)
    except PathAccessError:
        return
    assert not (tmp_path.parent / "disari").exists(), "kök dışına yazdı"


def test_iskeleden_sonra_write_file_calisir(tmp_path):
    """İskele yazıldıktan sonra model dosyaları normal araçlarla doldurabilmeli."""
    context = ToolContext(root=tmp_path)
    scaffold_web({"path": "."}, context)

    sonuc = file_tools.write_file({"path": "style.css", "content": ".x{}"}, context)

    assert sonuc.ok


def test_iskele_dosyadan_acilinca_calisir(tmp_path):
    """ES modülleri file:// protokolünde CORS ile ENGELLENİR.

    Gerçek hata: iskele `<script type="module">` + `import` kullanıyordu; kullanıcı
    index.html'i çift tıklayıp açtığında JavaScript hiç yüklenmedi ve iki bölüm boş
    kaldı. Üretilen sayfa sunucusuz da açılabilmelidir.
    """
    context = ToolContext(root=tmp_path)
    scaffold_web({"path": "."}, context)

    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    js = (tmp_path / "format.js").read_text(encoding="utf-8")

    assert 'type="module"' not in html, "modül tipi file:// altında çalışmaz"
    assert "export " not in js, "export ES modülü gerektirir"
    assert "format.js" in html, "format.js doğrudan bağlanmalı"


def test_iskelet_scriptleri_dogru_sirada_bagliyor(tmp_path):
    """format.js, onu kullanan script.js'ten ÖNCE yüklenmeli."""
    context = ToolContext(root=tmp_path)
    scaffold_web({"path": "."}, context)

    html = (tmp_path / "index.html").read_text(encoding="utf-8")

    assert html.index("format.js") < html.index("script.js")


def test_yer_tutucu_gorsel_fonksiyonu_var(tmp_path):
    """Model elle SVG yazınca <rect>'i kapatmadı ve 12 görselin 8'i yüklenmedi."""
    context = ToolContext(root=tmp_path)
    scaffold_web({"path": "."}, context)

    js = (tmp_path / "format.js").read_text(encoding="utf-8")

    assert "placeholderImage" in js
    assert "encodeURIComponent" in js, "elle kaçış hataya açık"


def test_tokens_mobil_menuyu_masaustunde_gizler(tmp_path):
    """Gizlenmezse header'ın altında 1440x284 boş bant kalıyor."""
    context = ToolContext(root=tmp_path)
    scaffold_web({"path": "."}, context)

    css = (tmp_path / "tokens.css").read_text(encoding="utf-8")

    assert ".mobile-menu { display: none; }" in css
    assert "max-width: 768px" in css


def test_tokens_yandan_panel_stili_tasiyor(tmp_path):
    """Sepet paneli fixed olmazsa footer'ın altına düşüyor."""
    context = ToolContext(root=tmp_path)
    scaffold_web({"path": "."}, context)

    css = (tmp_path / "tokens.css").read_text(encoding="utf-8")

    assert ".drawer" in css and "position: fixed" in css


def test_tokens_fiyat_stilleri_ayrik(tmp_path):
    """line-through YALNIZCA eski fiyata; model tüm bloğa sarıyordu."""
    context = ToolContext(root=tmp_path)
    scaffold_web({"path": "."}, context)

    css = (tmp_path / "tokens.css").read_text(encoding="utf-8")

    assert ".price__old" in css and "line-through" in css
    assert ".price__now" in css
