import { z } from 'zod';

/**
 * Kit'in, kullanıcının GERÇEK Chrome'una (Fusion Chrome eklentisi) erişimi (P-063).
 *
 * Kit'in kendi tarayıcısı (computer_*) oturumsuz ve ayrıdır; bu araç kullanıcının açık
 * oturumlarını (Gmail, yönetim panelleri…) Fusion uygulaması üzerinden kullanır. Her
 * istek iframe'den Fusion hostuna gider, host kullanıcıya sorar, onaylanırsa komutu
 * oturumun Chrome köprüsüne iletir ve yalnız metin döner (ekran görüntüsü taşınmaz).
 * Yalnız Fusion uygulamasının içinde çalışır.
 */
export const FUSION_BROWSER_ACTIONS = [
  'read',
  'find',
  'text',
  'tabs',
  'scroll',
  'navigate',
  'click',
  'type',
  'key',
] as const;
export type FusionBrowserAction = (typeof FUSION_BROWSER_ACTIONS)[number];
/** Sayfayı değiştirmeyen eylemler; host bunları bir kez onaylatıp hatırlayabilir. */
export const FUSION_BROWSER_READ_ACTIONS: ReadonlySet<FusionBrowserAction> =
  new Set(['read', 'find', 'text', 'tabs', 'scroll']);

export const fusionBrowserSchema = z
  .object({
    action: z.enum(FUSION_BROWSER_ACTIONS),
    /** `read`/`find` çıktısındaki öğe kimliği (e3 gibi); click/type/key için. */
    ref: z.string().min(1).max(100).optional(),
    /** find: aranan metin; type: yazılacak metin; key: tuş (Enter, Escape, Tab…);
     * scroll: up|down|left|right[:piksel]; text: sayfa numarası. */
    value: z.string().max(16000).optional(),
    /** navigate için adres (http/https). */
    url: z.string().max(2048).optional(),
    /** Kullanıcıya gösterilen kısa gerekçe. */
    reason: z.string().trim().max(300).optional(),
  })
  .strict();
export type FusionBrowserInput = z.infer<typeof fusionBrowserSchema>;

/** Fusion izni kapalı Kit'e dönen metin; ayarın yerini söyler. */
export const FUSION_BROWSER_NOT_ALLOWED =
  "Bu Kit'in Fusion izni kapalı; Kit ayarlarından (Kit'i düzenle > Fusion) açınca kullanıcının Chrome'u kullanılabilir.";

export interface FusionBrowserResult {
  status: 'ok' | 'denied' | 'busy' | 'failed' | 'unavailable';
  text: string;
}

export const fusionBrowserTool = {
  name: 'fusion_browser',
  description:
    "Use the owner's own Chrome (real logged-in sessions) through the Fusion app. Actions: read (page text and interactive elements with refs), find (value=search text), text (value=page number of full text), tabs, scroll (value=up|down|left|right[:px]), navigate (url), click (ref), type (ref, value), key (value=Enter/Escape/Tab…, optional ref). Fusion asks the owner for permission; interactive actions are confirmed every time. Returns text only. Give a short reason. Only works inside the Fusion app; use computer_* tools for the Kit's own isolated browser.",
  parameters: z.toJSONSchema(fusionBrowserSchema),
};
