"""Render — satır bütünlüğü ve kanal ayrımı (eski "anlamsız görüntü" hatasının testi)."""

from __future__ import annotations

import io

from rich.console import Console

from fusion_cli.core.events import (
    Channel,
    ErrorOccurred,
    ModelCallFinished,
    ModelCallStarted,
    SelfReviewFinished,
    StatusChanged,
    TokenReceived,
    TurnFinished,
)
from fusion_cli.core.types import ModelResult, TokenUsage
from fusion_cli.ui import theme
from fusion_cli.ui.renderer import ConsoleRenderer

#: Cevabın başındaki işaret; akan metnin önüne konur.
MARK = theme.ICON_ANSWER


def _renderer():
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=200, no_color=True)
    return ConsoleRenderer(console), buffer


def test_yarim_satir_varken_durum_satiri_metnin_ustune_binmez():
    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "yarim cumle"))
    renderer.handle(StatusChanged("araç çalıştı"))
    renderer.handle(TurnFinished())  # bekleyen durum satırını boşaltır

    satirlar = buffer.getvalue().splitlines()
    assert satirlar[0] == f"{MARK} yarim cumle"
    assert "araç çalıştı" in satirlar[1]


def test_tam_satirdan_sonra_bos_satir_eklenmez():
    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "tam satir\n"))
    renderer.handle(StatusChanged("durum"))

    assert buffer.getvalue().splitlines()[0] == f"{MARK} tam satir"


def test_kanal_degisiminde_satir_kapatilir_ve_baslik_basilir():
    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "ana akis"))
    renderer.handle(TokenReceived(Channel.SUBAGENT, "alt akis"))

    satirlar = buffer.getvalue().splitlines()
    assert satirlar[0] == f"{MARK} ana akis"
    assert "alt-ajan" in satirlar[1]
    assert satirlar[2] == "alt akis"


def test_ayni_kanalda_pespese_parcalar_birlesir():
    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "mer"))
    renderer.handle(TokenReceived(Channel.MAIN, "haba"))
    renderer.handle(TurnFinished())

    assert buffer.getvalue().splitlines()[0] == f"{MARK} merhaba"


def test_model_ciktisindaki_koseli_parantez_markup_sanilmaz():
    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "dizi[0] ve [bold] metni\n"))

    assert "dizi[0] ve [bold] metni" in buffer.getvalue()


def test_hata_mesajindaki_markup_yorumlanmaz():
    renderer, buffer = _renderer()

    renderer.handle(ErrorOccurred("beklenmedik [token] geldi"))

    assert "[token]" in buffer.getvalue()


def test_basarili_model_cagrisi_sure_ve_token_gosterir():
    """Ayrıntı yalnızca fusion modunda basılır; agent'ta tur özeti yeterli."""
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=200, no_color=True)
    renderer = ConsoleRenderer(console, show_call_details=True)
    result = ModelResult(
        name="agent",
        model="m",
        text="x",
        latency_ms=2900,
        ok=True,
        usage=TokenUsage(prompt_tokens=3, completion_tokens=7),
    )

    renderer.handle(ModelCallFinished(role="agent", result=result))
    renderer.handle(TurnFinished())

    cikti = buffer.getvalue()
    assert "2.9s" in cikti and "10" in cikti


def test_agent_modunda_adim_ayrintisi_basilmaz():
    """Her adım için satır basmak tur özetiyle çakışıyor ve gürültü oluyor."""
    renderer, buffer = _renderer()
    result = ModelResult(name="agent", model="m", text="x", latency_ms=100, ok=True)

    renderer.handle(ModelCallFinished(role="agent", result=result))

    assert buffer.getvalue() == ""


def test_basarisiz_cagri_moddan_bagimsiz_gosterilir():
    """Hata her zaman görünmeli; sessizce yutulamaz."""
    renderer, buffer = _renderer()
    result = ModelResult(name="a", model="m", text="", latency_ms=1, ok=False, error="ag yok")

    renderer.handle(ModelCallFinished(role="a", result=result))

    assert "ag yok" in buffer.getvalue()


def test_model_cagri_baslangici_basilmaz():
    """Yedek zinciriyle birlikte model kimliği ekranı kaplıyordu."""
    from fusion_cli.core.events import ModelCallStarted

    renderer, buffer = _renderer()

    renderer.handle(ModelCallStarted(role="agent", model="a/b | c/d | e/f"))

    assert buffer.getvalue() == ""


def test_uzun_saglayici_hatasi_ozetlenir():
    renderer, buffer = _renderer()
    uzun = (
        "RateLimitError: litellm.RateLimitError: OpenrouterException - "
        '{"error":{"message":"Rate limit exceeded","code":429}} LiteLLM Retried: 1 times'
    )
    result = ModelResult(name="a", model="m", text="", latency_ms=1, ok=False, error=uzun)

    renderer.handle(ModelCallFinished(role="a", result=result))

    cikti = buffer.getvalue()
    assert "RateLimitError" in cikti
    assert "LiteLLM Retried" not in cikti
    assert len(cikti) < 200


def test_quiet_modda_durum_basilmaz_ama_metin_akar():
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=200, no_color=True)
    renderer = ConsoleRenderer(console, show_progress=False)

    renderer.handle(StatusChanged("gizli"))
    renderer.handle(TokenReceived(Channel.MAIN, "gorunur\n"))

    cikti = buffer.getvalue()
    assert "gizli" not in cikti
    assert "gorunur" in cikti


def _fusion_sonuc(**overrides):
    from fusion_cli.core.types import FusionResult, ModelResult, VerdictSource

    aday = ModelResult(name="a", model="m", text="A cevabi", latency_ms=10, ok=True)
    defaults = {
        "task": "t",
        "task_type": "general",
        "winner": "a",
        "final_answer": "nihai cevap",
        "source": VerdictSource.JUDGE,
        "candidates": (aday,),
        "reason": "a daha net anlatmis",
        "scores": {"a": 0.9},
        "synthesized": False,
    }
    defaults.update(overrides)
    return FusionResult(**defaults)


def test_sentez_gosterilirken_hakem_gerekcesi_basilmaz():
    from fusion_cli.core.events import FusionCompleted

    renderer, buffer = _renderer()

    renderer.handle(FusionCompleted(_fusion_sonuc(synthesized=True)))

    cikti = buffer.getvalue()
    assert "sentez" in cikti
    # Gerekçe kazananı anlatır; sentez metninin yanında gösterilmesi yanıltıcı olur.
    assert "a daha net anlatmis" not in cikti


def test_sentez_yokken_hakem_gerekcesi_basilir():
    from fusion_cli.core.events import FusionCompleted

    renderer, buffer = _renderer()

    renderer.handle(FusionCompleted(_fusion_sonuc()))

    cikti = buffer.getvalue()
    assert "kazanan: a" in cikti
    assert "a daha net anlatmis" in cikti


def test_cevapsiz_turda_fusion_bloku_basilmaz():
    from fusion_cli.core.events import FusionCompleted
    from fusion_cli.core.types import VerdictSource

    renderer, buffer = _renderer()

    renderer.handle(FusionCompleted(_fusion_sonuc(source=VerdictSource.NONE, final_answer="")))

    assert buffer.getvalue().strip() == ""


def test_tum_cevaplar_secenegi_aday_metinlerini_gosterir():
    from fusion_cli.core.events import FusionCompleted

    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=200, no_color=True)
    renderer = ConsoleRenderer(console, show_all_answers=True)

    renderer.handle(FusionCompleted(_fusion_sonuc()))

    assert "A cevabi" in buffer.getvalue()


def test_puan_tablosu_kazanani_isaretler():
    from fusion_cli.core.events import FusionCompleted

    renderer, buffer = _renderer()

    renderer.handle(FusionCompleted(_fusion_sonuc()))

    assert "0.90" in buffer.getvalue()


# --- Düşünme metni ayıklama --------------------------------------------------- #


def test_kapali_dusunme_blogu_gosterilmez():
    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "<think>uzun uzun dusunuyorum</think>Cevap: 42\n"))

    cikti = buffer.getvalue()
    assert "dusunuyorum" not in cikti
    assert "Cevap: 42" in cikti


def test_kapanmamis_dusunme_blogu_sizdirilmaz():
    """Akış sürerken kapanış gelebilir; kapanmamış açılıştan sonrası tutulur."""
    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "Basliyorum. <think>gizli olmali"))

    cikti = buffer.getvalue()
    assert "Basliyorum." in cikti
    assert "gizli" not in cikti


def test_dusunme_parca_parca_gelse_de_gizlenir():
    renderer, buffer = _renderer()

    for parca in ("<th", "ink>giz", "li plan</thi", "nk>Gorunur cevap\n"):
        renderer.handle(TokenReceived(Channel.MAIN, parca))

    cikti = buffer.getvalue()
    assert "gizli plan" not in cikti
    assert "Gorunur cevap" in cikti


def test_dusunme_sonrasi_metin_tekrar_basilmaz():
    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "onsoz "))
    renderer.handle(TokenReceived(Channel.MAIN, "<think>ara dusunce</think>"))
    renderer.handle(TokenReceived(Channel.MAIN, "sonrasi\n"))

    assert buffer.getvalue().count("onsoz") == 1


def test_tur_bitince_tampon_temizlenir():
    from fusion_cli.core.events import TurnFinished

    renderer, buffer = _renderer()
    renderer.handle(TokenReceived(Channel.MAIN, "ilk tur\n"))
    renderer.handle(TurnFinished())
    renderer.handle(TokenReceived(Channel.MAIN, "ikinci tur\n"))

    satirlar = [satir for satir in buffer.getvalue().splitlines() if satir.strip()]
    assert satirlar == [f"{MARK} ilk tur", f"{MARK} ikinci tur"]


def test_dusunmeyle_ilgisiz_kucuktur_isareti_kaybolmaz():
    """`<` ile biten gerçek bir cevap tur sonunda serbest bırakılmalı."""
    from fusion_cli.core.events import TurnFinished

    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "sonuc: a < b"))
    renderer.handle(TurnFinished())

    assert "a < b" in buffer.getvalue()


def test_dusunme_blogu_olmadan_metin_aynen_akar():
    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "duz cevap\n"))

    assert buffer.getvalue().splitlines()[0] == f"{MARK} duz cevap"


# --- Çalışma göstergesi ile akış çakışması ------------------------------------ #


class _SpyIndicator:
    """Göstergenin YARIM SATIR üstünde başlatılıp başlatılmadığını izler."""

    def __init__(self, renderer):
        self._renderer = renderer
        self.running = False
        self.resumed_on_open_line = False

    def start(self, label, *, model=""):
        self.running = True
        if self._renderer._line_open:
            self.resumed_on_open_line = True

    def update(self, **kwargs):
        return None

    def pause(self):
        return None

    def resume(self):
        if self._renderer._line_open:
            self.resumed_on_open_line = True

    def finish(self):
        return None


def _renderer_with_spy():
    renderer, buffer = _renderer()
    spy = _SpyIndicator(renderer)
    renderer._work = spy
    return renderer, buffer, spy


def test_gosterge_yarim_satirin_ustunde_baslatilmaz():
    """Regresyon: Rich Live `transient` modda durunca çizdiği satırı siler.

    Satır ortasında başlatılırsa modelin cevabını silip götürüyordu — gerçek bir
    turda cevap ekrandan kayboldu.
    """
    from fusion_cli.core.events import SelfReviewStarted

    renderer, _, spy = _renderer_with_spy()

    renderer.handle(TokenReceived(Channel.MAIN, "yarim kalan cevap"))  # newline YOK
    renderer.handle(SelfReviewStarted())

    assert not spy.resumed_on_open_line


def test_arac_sonrasi_gosterge_yarim_satirin_ustunde_baslatilmaz():
    from fusion_cli.core.events import ToolExecuted, ToolOutcome

    renderer, _, spy = _renderer_with_spy()

    renderer.handle(TokenReceived(Channel.MAIN, "yarim"))
    renderer.handle(
        ToolExecuted(name="read_file", args={"path": "a"}, outcome=ToolOutcome.OK, output="x")
    )

    assert not spy.resumed_on_open_line


def test_model_cagrisi_gosterge_yarim_satirin_ustunde_baslatilmaz():
    from fusion_cli.core.events import ModelCallStarted

    renderer, _, spy = _renderer_with_spy()

    renderer.handle(TokenReceived(Channel.MAIN, "yarim"))
    renderer.handle(ModelCallStarted(role="agent", model="m"))

    assert not spy.resumed_on_open_line


def test_cevap_metni_tur_boyunca_korunur():
    """Akan cevap, gösterge ve öz-denetim olaylarından sonra da ekranda kalmalı."""
    from fusion_cli.core.events import (
        ModelCallStarted,
        SelfReviewFinished,
        SelfReviewStarted,
        TurnFinished,
    )

    renderer, buffer = _renderer()

    renderer.handle(ModelCallStarted(role="agent", model="m"))
    renderer.handle(TokenReceived(Channel.MAIN, "Merhaba, ben Fusion."))
    renderer.handle(SelfReviewStarted())
    renderer.handle(SelfReviewFinished(issue_found=False))
    renderer.handle(TurnFinished())

    assert "Merhaba, ben Fusion." in buffer.getvalue()


# --- Kullanıcı mesajı bandı ---------------------------------------------------- #


def test_kullanici_mesaji_tam_genislikte_bant_olur():
    """Konuşmanın kimin sözü olduğu tek bakışta görünmeli."""
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=60, no_color=True)
    renderer = ConsoleRenderer(console)

    renderer.print_user_message("Merhaba")

    bant = next(satir for satir in buffer.getvalue().splitlines() if "Merhaba" in satir)
    assert bant.startswith(f" {theme.ICON_PROMPT} Merhaba")
    # Zeminin tüm satırı kaplaması için sağa doldurulur.
    assert len(bant) == 60


def test_kullanici_mesajinin_etrafinda_nefes_birakilir():
    renderer, buffer = _renderer()

    renderer.print_user_message("Merhaba")

    satirlar = buffer.getvalue().splitlines()
    assert satirlar[0].strip() == ""
    assert satirlar[-1].strip() == ""


def test_bant_yarim_kalan_akisin_uzerine_binmez():
    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "yarim cevap"))
    renderer.print_user_message("yeni mesaj")

    satirlar = [satir for satir in buffer.getvalue().splitlines() if satir.strip()]
    assert satirlar[0] == f"{MARK} yarim cevap"


def test_araya_giren_ciktidan_sonra_cevap_yeni_blok_olur():
    """Düzeltici turun cevabı işaretsiz kalıp öncekinin devamı gibi görünüyordu."""
    from fusion_cli.core.events import SelfReviewFinished

    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "ilk cevap\n"))
    renderer.handle(SelfReviewFinished(issue_found=True))
    renderer.handle(TokenReceived(Channel.MAIN, "duzeltilmis cevap\n"))

    satirlar = [satir for satir in buffer.getvalue().splitlines() if satir.strip()]
    assert satirlar[0] == f"{MARK} ilk cevap"
    assert satirlar[-1] == f"{MARK} duzeltilmis cevap"


def test_kesintisiz_akis_tek_isaret_alir():
    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "bir "))
    renderer.handle(TokenReceived(Channel.MAIN, "iki\n"))

    assert buffer.getvalue().count(MARK) == 1


# --- Özet satırı --------------------------------------------------------------- #


def test_ozet_son_durum_satirinin_yanina_parantezle_girer():
    """İki ayrı satır ekranı gereksiz uzatıyordu."""
    renderer, buffer = _renderer()

    renderer.handle(ModelCallStarted(role="nemotron", model="nemotron"))
    renderer.handle(SelfReviewFinished(issue_found=False))
    renderer.handle(TurnFinished())

    satirlar = [satir for satir in buffer.getvalue().splitlines() if satir.strip()]
    assert satirlar[-1].count("(") == 1
    assert satirlar[-1].endswith(")")
    assert "öz-denetim" in satirlar[-1]


def test_durum_satiri_yoksa_ozet_kendi_satirinda_basilir():
    renderer, buffer = _renderer()

    renderer.handle(ModelCallStarted(role="nemotron", model="nemotron"))
    renderer.handle(TurnFinished())

    satirlar = [satir for satir in buffer.getvalue().splitlines() if satir.strip()]
    assert satirlar[-1].strip().startswith(theme.ICON_DONE)


def test_bekleyen_durum_satiri_cevabin_uzerine_binmez():
    """Geciktirme sırayı bozmamalı: durum satırı kendinden sonraki metinden önce."""
    renderer, buffer = _renderer()

    renderer.handle(StatusChanged("araç çalıştı"))
    renderer.handle(TokenReceived(Channel.MAIN, "cevap\n"))
    renderer.handle(TurnFinished())

    satirlar = [satir for satir in buffer.getvalue().splitlines() if satir.strip()]
    assert "araç çalıştı" in satirlar[0]
    assert satirlar[1] == f"{MARK} cevap"
