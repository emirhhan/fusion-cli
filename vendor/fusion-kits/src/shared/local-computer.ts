import { z } from 'zod';
export const localComputerSchema = z
  .object({ reason: z.string().trim().min(1).max(300) })
  .strict();
/** Kullanıcının kendi Mac'ine salt okunur bakış: ekran + öndeki pencerenin öğeleri.
 * Her çağrıda Fusion uygulaması kullanıcıya sorar; tıklama/yazma yetkisi yoktur. */
export const localComputerTool = {
  name: 'look_at_my_computer',
  description:
    "Look at the owner's own Mac (read-only): returns the frontmost app/window and its accessibility elements. The Fusion app asks the owner for permission every time; it cannot click or type. Give a short reason. Only works inside the Fusion app.",
  parameters: z.toJSONSchema(localComputerSchema),
};
