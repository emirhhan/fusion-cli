"""Gateway panel durumu: tazeleme kullanıcı düzenlemesini silmez, hata görünür (Z1-44..Z1-46).

Ölçüldü (30 Ekim): `render()` her 5 sn'lik `load()` çağrısında zincir/hakem/strateji
değişkenlerini sunucudan yeniden atıyor (kaydedilmemiş düzenleme siliniyordu); `load()`
sunucu kapandığında hatayı yutup 'yerel · çalışıyor' rozetini koruyordu.
"""

from __future__ import annotations

from tests.gateway_panel_harness import calistir, node_gerekli

pytestmark = node_gerekli

_DURUM = """
const durum = {
  providers: [], models: ['a', 'b'], routing: { current: 'priority', options: ['priority', 'free_first'] },
  fallback: ['a', 'b'], judge: ['j1'], health: [], analytics: {}, version: '1', config_path: '',
  secret_ready: true, strict_model_selection: false, mcp_servers: [],
};
let sunucuAcik = true;
globalThis.fetch = async (url, opts) => {
  if (!sunucuAcik) throw new Error('baglanti yok');
  return { ok: true, status: 200, headers: { get: () => '' }, json: async () => (url === '/api/state' ? durum : {}) };
};
"""


def test_tazeleme_kaydedilmemis_zincir_duzenlemesini_silmez() -> None:
    sonuc = calistir(
        _DURUM
        + """
        await load();
        $('newModel').value = 'yeni-model';
        addChain();
        await load();            // 5 sn'lik canlı tazeleme
        const tazelemeSonrasi = chain.slice();
        await saveFallback();    // kaydedince sunucu durumu geçerli olur
        await load();
        return { tazelemeSonrasi, kaydetSonrasi: chain.slice() };
        """
    )
    assert sonuc == {"tazelemeSonrasi": ["a", "b", "yeni-model"], "kaydetSonrasi": ["a", "b"]}


def test_tazeleme_kaydedilmemis_hakem_ve_stratejiyi_silmez() -> None:
    sonuc = calistir(
        _DURUM
        + """
        await load();
        $('newJudge').value = 'j2';
        addJudge();
        $('strategy').value = 'free_first';
        markRoutingDirty();
        await load();
        return { judge: judge.slice(), strateji: $('strategy').value };
        """
    )
    assert sonuc == {"judge": ["j1", "j2"], "strateji": "free_first"}


def test_sunucu_kapaninca_rozet_ve_uyari_guncellenir() -> None:
    sonuc = calistir(
        _DURUM
        + """
        await load();
        const once = $('statusPill').textContent;
        sunucuAcik = false;
        await load();
        const kapali = { metin: $('statusPill').textContent, sinif: $('statusPill').className };
        sunucuAcik = true;
        await load();
        return { once, kapali, sonra: $('statusPill').textContent };
        """
    )
    assert isinstance(sonuc, dict)
    assert sonuc["once"] == "yerel · çalışıyor"
    assert "bağlantı yok" in sonuc["kapali"]["metin"]
    assert "off" in sonuc["kapali"]["sinif"]
    assert sonuc["sonra"] == "yerel · çalışıyor"


def test_sohbet_hata_govdesi_ham_json_degil_mesaj_gosterir() -> None:
    sonuc = calistir(
        """
        globalThis.fetch = async () => ({ ok: false, status: 502, headers: { get: () => '' },
          json: async () => ({ error: { message: 'Sağlayıcı yanıt vermedi.' } }) });
        $('chatModel').value = 'm'; $('chatMsg').value = 'merhaba';
        await sendChat();
        return $('chatOut').textContent;
        """
    )
    assert sonuc == "hata: Sağlayıcı yanıt vermedi."


def test_post_hata_mesaji_http_durum_kodunu_icerir() -> None:
    sonuc = calistir(
        """
        globalThis.fetch = async () => ({ ok: false, status: 503, json: async () => { throw new Error('html'); } });
        try { await post('/api/x', {}); return 'hata-yok'; } catch (e) { return e.message; }
        """
    )
    assert "503" in str(sonuc)


def test_ardisik_toast_eski_zamanlayiciyla_kapanmaz() -> None:
    sonuc = calistir(
        """
        const zamanlayicilar = [];
        ctx = globalThis;
        globalThis.setTimeout = (fn, ms) => { zamanlayicilar.push({ fn, iptal: false }); return zamanlayicilar.length; };
        globalThis.clearTimeout = (id) => { if (zamanlayicilar[id - 1]) zamanlayicilar[id - 1].iptal = true; };
        toast('bir');
        toast('iki');
        return { sayi: zamanlayicilar.length, ilkIptal: zamanlayicilar[0].iptal };
        """
    )
    assert sonuc == {"sayi": 2, "ilkIptal": True}
