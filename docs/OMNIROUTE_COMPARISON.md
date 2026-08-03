# Fusion ↔ OmniRoute — Dürüst Karşılaştırma

> OmniRoute (github.com/diegosouzapw/OmniRoute) bir **AI gateway sunucusu** (Next.js +
> Electron + PWA); tek yerel `/v1` uç noktası açar, başka araçlar ona bağlanır. Fusion
> bir **kodlama agent'ı** + gömülü router. Bu belge ikisini gerçek durumla eşler.

## Fusion'da artık VAR (gateway dönüşümü sonrası)

| OmniRoute özelliği | Fusion |
|---|---|
| Tek yerel OpenAI-uyumlu `/v1` uç noktası | ✅ `fusion serve` (yalnız 127.0.0.1) |
| Yerelde çalışan web paneli | ✅ `/dashboard` (sağlayıcı/sağlık/model) |
| Çoklu routing stratejisi | ✅ 6 strateji (priority/free_first/headroom/least_used/round_robin/random) |
| Route kararı header'ı (X-OmniRoute-Decision) | ✅ `X-Fusion-Route` |
| 290 sağlayıcı | ⚠️ 48 (gerçek, LiteLLM ile çalışır) |
| Quota-aware auto-fallback | ✅ fallback + circuit breaker + health |
| 3-katman resilience (breaker/cooldown/lockout) | ✅ circuit breaker + reliability + retry |
| AES-256-GCM şifreli anahtar | ✅ Fernet şifreli credential store |
| Protokol çevirisi (OpenAI/Claude/Gemini) | ✅ LiteLLM (core.types canonical) |
| Maliyet/kullanım telemetrisi | ✅ temel (CostTracker) |

## Fusion'ın FAZLASI (OmniRoute'ta yok)

OmniRoute bir agent değildir. Fusion'da **tüm agentic kodlama motoru** var: araçlar,
dosya düzenleme, shell, git, plan modu, öz-denetim, doğrulama kapısı, playbook, skill,
subagent, öz-öğrenen bellek/dersler, kod indeksi + **Fusion/Council** (çok-model hakem).

## Hâlâ eksik (dürüst)

| OmniRoute | Durum / karar |
|---|---|
| 290 sağlayıcı / 90+ ücretsiz katman canlı takibi | Kısmi (48); serbest-katman bütçe paneli yok |
| 12-motor token sıkıştırma (RTK/Caveman/LLMLingua) | Temel compaction var; agresif sıkıştırma kodu bozar diye yapılmadı |
| Hesap/anahtar havuzu + fair-share kota | Yok (provider başına tek anahtar) |
| MCP sunucusu (104 tool) / A2A protokolü | Tool/subagent var; sunucu/A2A yok |
| 43 dil i18n | TR/EN |
| TLS stealth / MITM-TPROXY (başka CLI'yı yakalama) | **Yapılmadı — bilerek** (senin "rootlamadan" hedefinle çelişir) |
| Çalışan tüketici web-session (ChatGPT/Gemini web) | **Yapılmadı — ToS**; framework hazır, transport'u kullanıcı sağlar |

## Nasıl kullanılır (yerel, senin bilgisayarında)

```bash
pip install 'fusion-cli[gateway]'
fusion serve                     # http://127.0.0.1:8787/v1  + /dashboard

# Herhangi bir OpenAI-uyumlu araç:
#   base_url = http://127.0.0.1:8787/v1
#   model    = auto | low | medium | high | max | ham-kimlik (openai/gpt-4o, …)
```

Uzak/paylaşımlı sunucu değildir; her şey senin makinende çalışır — tıpkı OmniRoute gibi.
