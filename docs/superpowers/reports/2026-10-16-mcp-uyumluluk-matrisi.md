# MCP uyumluluğu — 16 Ekim 2026

| Katman | Doğrulanan sürüm | Sunulan protokol | Karar |
| --- | --- | --- | --- |
| Python ortamı | Kurulu mcp 1.30.0; pyproject `>=1.9,<2` | SDK sabiti 2025-11-25 | Mevcut initialize/initialized otoritesi korunur. Python uv.lock yok; kurulu sürüm lock kanıtı değildir. |
| Kits | package-lock içindeki SDK 1.31.0 | Kurulu SDK sabiti 2025-11-25 | Mevcut istemci ve host origin politikası korunur. |
| 2026-07-28 | Resmî şartname mevcut | Yeni stateless çekirdek | Bu kurulumda destek ilan edilmez; deneysel geçiş kapısı kapalıdır. |

Yeni şartname initialize ve oturum başlığını kaldırıyor; istek yönlendirme başlıkları ve istemci meta verisi getiriyor. Mevcut v1 SDK oturumuna yalnız yeni başlıkları eklemek bu desteği sağlamaz. Kaynaklar: [resmî sürüm duyurusu](https://blog.modelcontextprotocol.io/posts/2026-07-28/) ve [temel şartname](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/index.mdx).

## Açılma koşulları

1. SDK yükseltmesi ayrı değişiklikte çözülür ve sabitlenir; mevcut auth/trust/iptal davranışları tekrar sınanır.
2. Yeni adaptör gerçek HTTP fixture'da initialize/initialized ve Mcp-Session-Id göndermediğini kanıtlar.
3. MCP-Protocol-Version, Mcp-Method, gerekli Mcp-Name ve `_meta` değerleri body/header ile tutarlı olmalıdır.
4. İsteğe bağlı server/discover olmadan çağrı ve keşifle çağrı ayrı sınanır. MRTR input_required sessiz başarıya veya kör yeniden dış etkiye dönüşmez.
5. Legacy STDIO/HTTP fixture ve yeni stateless fixture ayrı kalır. Yeni adaptörün başarısızlığı çalışan legacy bağlayıcıları devre dışı bırakmaz.

Bu kayıt migration kararını ve mevcut desteği belgelemektedir; yeni protokolün uygulanmış veya test edilmiş olduğu anlamına gelmez. Günlük sürümde desteklenmeyen bir seçenek gösterilmez. Kullanıcının mevcut hesabı/modeli ve bağlı sunucuları sessizce değiştirilmez.
