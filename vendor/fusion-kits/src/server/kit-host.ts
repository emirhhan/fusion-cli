import type { LocalComputerPolicy } from './kit-tool-gate.js';
export interface KitRunIdentity {
  readonly ownerId: string;
  readonly dotId: string;
  readonly threadId: string;
}
/** Uygulama hostu enjekte eder; model/RPC verisi yerellik yetkisi değildir. */
export type KitPolicyFactory = (
  identity: KitRunIdentity,
) => LocalComputerPolicy;
export interface KitHostDependencies {
  readonly localComputerPolicy: KitPolicyFactory;
}
