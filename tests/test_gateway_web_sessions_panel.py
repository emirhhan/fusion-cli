"""Gateway web oturumu paneli: ölçüm onayı, giriş yoklaması, erken modal (Z1-47, Z1-48, Z1-50).

Ölçüldü (30 Ekim): 'Araç yeteneğini ölç' 5 gerçek istek gönderip abonelik kotası harcıyor ama onay
istemiyordu; `awaitLoginThenValidate` yoklama hatasında sessizce dönüyordu; durum yüklenmeden
açılan kurulum penceresi `STATE.web_sessions` okurken TypeError veriyordu.
"""

from __future__ import annotations

from tests.gateway_panel_harness import calistir, node_gerekli

pytestmark = node_gerekli

_HAZIR = """
const cagrilar = [];
globalThis.fetch = async (url, opts) => {
  cagrilar.push(url);
  if (url === '/api/web_sessions') return { ok: true, status: 200, json: async () => ({}) };
  if (url === '/api/state') return { ok: true, status: 200, json: async () => ({
    providers: [], models: [], routing: { current: 'priority', options: [] }, fallback: [], judge: [],
    health: [], analytics: {}, version: '1', web_sessions: [], mcp_servers: [] }) };
  if (url === '/api/web_sessions/eval') return { ok: true, status: 200, json: async () => ({
    ok: true, passed: true, scores: { tool_selection: 1, schema_validity: 1, argument_preservation: 1, no_false_calls: 1 },
    measured: { tool_selection: 3, schema_validity: 3, argument_preservation: 3, no_false_calls: 3 },
    thresholds: { tool_selection: 0.95, schema_validity: 0.97, argument_preservation: 0.98, no_false_calls: 0.99 }, samples: [] }) };
  return { ok: true, status: 200, json: async () => ({}) };
};
activeWebProvider = 'chatgpt_web';
$('nativeWebAccount').value = 'main';
$('nativeWebModel').value = 'chatgpt_web/main/auto';
$('nativeWebTimeout').value = '180';
"""


def test_arac_yetenegi_olcumu_onaysiz_istek_gondermez() -> None:
    sonuc = calistir(
        _HAZIR
        + """
        globalThis.confirm = () => false;
        await runWebEval();
        return cagrilar.filter((u) => u.includes('eval') || u === '/api/web_sessions');
        """
    )
    assert sonuc == []


def test_arac_yetenegi_olcumu_onaylaninca_calisir_ve_esikleri_gosterir() -> None:
    sonuc = calistir(
        _HAZIR
        + """
        let mesaj = '';
        globalThis.confirm = (m) => { mesaj = m; return true; };
        await runWebEval();
        return { mesaj, eval: cagrilar.includes('/api/web_sessions/eval'), durum: $('nativeWebStatus').textContent };
        """
    )
    assert isinstance(sonuc, dict)
    assert "5 gerçek istek" in sonuc["mesaj"]
    assert "kota" in sonuc["mesaj"]
    assert sonuc["eval"] is True
    assert "eşik 95%" in sonuc["durum"]


def test_giris_yoklamasi_ust_uste_basarisizsa_kullaniciya_bildirir() -> None:
    sonuc = calistir(
        _HAZIR
        + """
        globalThis.fetch = async () => { throw new Error('baglanti yok'); };
        globalThis.setTimeout = (fn) => { fn(); return 0; };
        await awaitLoginThenValidate(123);
        return $('nativeWebStatus').textContent;
        """
    )
    assert "izlenemiyor" in str(sonuc)
    assert "Bağlantıyı kontrol et" in str(sonuc)


def test_durum_yuklenmeden_kurulum_penceresi_acilirsa_cokmez() -> None:
    sonuc = calistir(
        """
        let acildi = false;
        globalThis.openModal = () => { acildi = true; };
        STATE = null;
        showWebSetup('chatgpt_web', null);
        return acildi;
        """
    )
    assert sonuc is False
