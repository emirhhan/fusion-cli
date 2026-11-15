import type { ToolDefinition } from '@copilotkit/runtime/v2';
import { resolveCapabilities, type KitManifest } from './kit-capabilities.js';
export interface ExecutionReceipt {
  readonly kit: string;
  readonly tool: string;
  readonly status: 'executed' | 'sample' | 'unverified' | 'failed' | 'blocked';
}
/** Yalnız güvenilir host enjekte eder; dış servis isteği bilgisayar hostu değildir. */
export interface LocalComputerPolicy {
  readonly manifest: KitManifest;
  readonly computerHost: () => 'local' | 'remote' | 'unknown';
  readonly permitted: (tool: string) => boolean;
  readonly receipt: (receipt: ExecutionReceipt) => void;
}
export function gateTools(
  tools: ToolDefinition[],
  policy: LocalComputerPolicy,
  check: () => void,
): ToolDefinition[] {
  const available = resolveCapabilities(
    policy.manifest,
    tools.map((tool) => tool.name),
    policy.permitted,
  );
  for (const capability of available) {
    if (capability.status !== 'available')
      policy.receipt({
        kit: policy.manifest.id,
        tool: capability.tool,
        status: 'blocked',
      });
  }
  return tools.map((tool) => {
    const execute = tool.execute;
    if (!execute) throw new Error(`Araç yürütücüsü yok: ${tool.name}`);
    return {
      ...tool,
      execute: async (input: unknown) => {
        const emit = (status: ExecutionReceipt['status']) =>
          policy.receipt({ kit: policy.manifest.id, tool: tool.name, status });
        const validate = () => {
          check();
          if (!policy.permitted(tool.name)) {
            emit('blocked');
            throw new Error('Araç izni kapalı.');
          }
          if (
            tool.name.startsWith('computer_') &&
            policy.computerHost() !== 'local'
          ) {
            emit('blocked');
            throw new Error(
              'Bilgisayar yürütmesi doğrulanmış yerel host gerektirir.',
            );
          }
        };
        validate();
        let result: unknown;
        try {
          result = await execute(input);
        } catch (error) {
          emit('failed');
          throw error;
        }
        validate();
        const record =
          typeof result === 'object' && result !== null
            ? (result as Record<string, unknown>)
            : undefined;
        emit(
          record?.sample === true
            ? 'sample'
            : record?.ok === false
              ? 'failed'
              : record?.sample === false || record?.ok === true
                ? 'executed'
                : 'unverified',
        );
        return result;
      },
    };
  });
}
