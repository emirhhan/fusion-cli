import { defineTool } from '@copilotkit/runtime/v2';
import { z } from 'zod';
import type { FusionService } from './service.js';

export function fusionTools(
  service: FusionService,
  dotId: string,
  threadId: string,
  check: () => void,
  signal: AbortSignal,
) {
  const projects = service.projects();
  const projectHint = projects.length
    ? ` Varsayılan kök dışında çalışmak için project alanına şu izinli adlardan birini ver: ${projects.join(', ')}.`
    : '';
  return [
    defineTool({
      name: 'fusion_run',
      description:
        'Kullanıcının açıkça istediği yerel kod veya proje görevini Fusion çekirdeğine devreder. Bu araç Dot bilgisayarından ayrıdır; sunucuda yapılandırılmış yerel proje kökünü kullanır. Kit ekranında insan onayı veya sorusu bekleyebilir. Space belgeleri için sayfa araçlarını, Dot bilgisayarı için computer araçlarını kullan. Görevi ve gerekli bağlamı prompt içinde ver; dosya değişikliklerini kanıt olmadan tamamlandı sayma. Sonuçtaki verification satırına uy: doğrulanmadıysa kullanıcıya tamamlandı deme, neyin doğrulanmadığını söyle.' +
        projectHint,
      parameters: z
        .object({
          prompt: z.string().trim().min(1).max(20000),
          project: z.string().max(64).optional(),
        })
        .strict(),
      execute: async ({ prompt, project }) => {
        check();
        return service.run(dotId, threadId, prompt, signal, project);
      },
    }),
  ];
}
