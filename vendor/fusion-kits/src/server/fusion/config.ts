import { isAbsolute } from 'node:path';

export interface FusionConfig {
  command: string;
  args: string[];
  root: string;
  home: string;
  requestTimeoutMs: number;
  maxLineBytes: number;
  shutdownTimeoutMs: number;
  /** Kullanıcının ana Fusion yapılandırması (MCP sunucuları, hesaplar); yoksa yalıtılmış ev. */
  userConfigHome?: string;
  /** Görevin seçebileceği ek proje kökleri (ad → mutlak yol); liste dışı kök yok. */
  projects: Record<string, string>;
}

function positive(
  env: Record<string, string | undefined>,
  key: string,
  fallback: number,
) {
  const value = Number(env[key] ?? fallback);
  if (!Number.isSafeInteger(value) || value <= 0)
    throw new Error(`${key} pozitif bir tam sayı olmalı.`);
  return value;
}

export function fusionConfig(
  env: Record<string, string | undefined>,
): FusionConfig | undefined {
  if (!Object.keys(env).some((key) => key.startsWith('FUSION_') && env[key]))
    return;
  if (!env.FUSION_COMMAND || !env.FUSION_ROOT || !env.FUSION_HOME)
    throw new Error(
      'Fusion bağlantısı için FUSION_COMMAND, FUSION_ROOT ve FUSION_HOME gerekli.',
    );
  if (
    !isAbsolute(env.FUSION_ROOT) ||
    !isAbsolute(env.FUSION_HOME) ||
    env.FUSION_ROOT === env.FUSION_HOME
  )
    throw new Error('Fusion kökü ve ev dizini farklı mutlak yollar olmalı.');
  let args: unknown;
  try {
    args = JSON.parse(env.FUSION_ARGS ?? '["app"]');
  } catch {
    throw new Error('FUSION_ARGS bir JSON argv dizisi olmalı.');
  }
  if (
    !Array.isArray(args) ||
    !args.every((value) => typeof value === 'string' && !value.includes('\0'))
  )
    throw new Error('FUSION_ARGS yalnız metinlerden oluşmalı.');
  return {
    command: env.FUSION_COMMAND,
    args,
    root: env.FUSION_ROOT,
    home: env.FUSION_HOME,
    // Denenen Fusion çekirdeği tek sağlayıcı çağrısını 600 sn bekleyebilir.
    // Toplam protokol bütçesi buna 60 sn oturum/araç işleme payı ekler.
    requestTimeoutMs: positive(env, 'FUSION_REQUEST_TIMEOUT_MS', 660_000),
    // Tek protokol satırı için sınır; dosya/araç çıktısı sınırsız birikmez.
    maxLineBytes: positive(env, 'FUSION_MAX_LINE_BYTES', 1_000_000),
    shutdownTimeoutMs: positive(env, 'FUSION_SHUTDOWN_TIMEOUT_MS', 3000),
    projects: projects(env),
    ...sharedConfig(env),
  };
}

// Açık izinle (FUSION_SHARE_USER_CONFIG=1) Kits, kullanıcının kendi Fusion
// yapılandırmasını görür: MCP sunucuları, barındırılan bağlayıcılar, hesaplar.
// Konuşma verisi ve bellek yine iş parçacığına özel yalıtılmış dizinde kalır.
function sharedConfig(env: Record<string, string | undefined>) {
  if (env.FUSION_SHARE_USER_CONFIG !== '1') return {};
  const home = env.FUSION_USER_HOME ?? env.HOME;
  if (!home || !isAbsolute(home))
    throw new Error(
      'FUSION_SHARE_USER_CONFIG için mutlak bir kullanıcı ev dizini gerekli.',
    );
  return { userConfigHome: home };
}

function projects(env: Record<string, string | undefined>) {
  if (!env.FUSION_PROJECTS) return {};
  let value: unknown;
  try {
    value = JSON.parse(env.FUSION_PROJECTS);
  } catch {
    throw new Error('FUSION_PROJECTS bir JSON nesnesi olmalı.');
  }
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('FUSION_PROJECTS ad → mutlak yol nesnesi olmalı.');
  const entries = Object.entries(value as Record<string, unknown>);
  for (const [name, path] of entries)
    if (
      !/^[\w.-]{1,64}$/u.test(name) ||
      typeof path !== 'string' ||
      !isAbsolute(path) ||
      path === env.FUSION_HOME
    )
      throw new Error(`FUSION_PROJECTS içindeki "${name}" geçersiz.`);
  return Object.fromEntries(entries) as Record<string, string>;
}
