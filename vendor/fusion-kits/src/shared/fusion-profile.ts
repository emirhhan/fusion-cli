import { z } from 'zod';

/**
 * Kit'in KENDİ tarayıcısına (computer_*) Fusion tarayıcı profili yüklemek (P-023).
 *
 * Fusion profilleri (girişli oturumlar) Fusion'da şifreli durur; anahtar Kit sürecine
 * açılmaz. Kit iframe'den Fusion hostuna sorar, Fusion kullanıcıya Kit adını, profili ve
 * alan adlarını gösterip HER seferinde onay ister. Onaylanırsa yalnız istenen alan
 * adlarının `storage_state`'i iframe'e bellek içi gelir; Kits sunucusu onu kalıcı olmayan
 * bir tarayıcı bağlamına verir (diske yazmaz, loglamaz). Kit'in modeli yalnız özet görür.
 * Tarayıcı kapanınca (boşta kalınca, Kit bilgisayarı durunca ya da sahip `session_clear`
 * deyince) oturum bellekten silinir.
 */
export const MAX_PROFILE_DOMAINS = 20;

export const fusionProfileSchema = z
  .object({
    /** Fusion'daki profil adı (Ayarlar › Web oturumları). */
    profile: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/),
    /** Oturumu istenen siteler (ör. example.com); alt alan adları kapsanır. */
    domains: z
      .array(z.string().trim().min(1).max(253))
      .min(1)
      .max(MAX_PROFILE_DOMAINS),
    /** Kullanıcıya gösterilen kısa gerekçe. */
    reason: z.string().trim().max(300).optional(),
  })
  .strict();
export type FusionProfileInput = z.infer<typeof fusionProfileSchema>;

/** Playwright `storageState` biçimi; Kits sunucusu yalnız bunu kabul eder. */
export const sessionStateSchema = z
  .object({
    cookies: z
      .array(
        z
          .object({
            name: z.string().min(1).max(4096),
            value: z.string().max(16384),
            domain: z.string().min(1).max(253),
            path: z.string().max(2048),
            expires: z.number().finite(),
            httpOnly: z.boolean(),
            secure: z.boolean(),
            sameSite: z.enum(['Strict', 'Lax', 'None']),
          })
          .strict(),
      )
      .max(2000),
    origins: z
      .array(
        z
          .object({
            origin: z.string().url().max(2048),
            localStorage: z
              .array(
                z
                  .object({
                    name: z.string().max(4096),
                    value: z.string().max(65536),
                  })
                  .strict(),
              )
              .max(500),
          })
          .strict(),
      )
      .max(100),
  })
  .strict();
export type SessionState = z.infer<typeof sessionStateSchema>;

export const fusionProfileTool = {
  name: 'fusion_profile',
  description:
    "Load one of the owner's Fusion browser profiles (logged-in sessions) into THIS Kit's own browser (computer_* tools) for the listed domains only. Fusion asks the owner every time and shows your Kit name, the profile and the domains. You never see cookie values; afterwards computer_navigate to the site is logged in. The session lives in memory and ends when the Kit browser closes. Give a short reason. Only works inside the Fusion app and needs the computer's browser permission.",
  parameters: z.toJSONSchema(fusionProfileSchema),
};
