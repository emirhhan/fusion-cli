export interface KitManifest {
  readonly id: string;
  readonly version: number;
  readonly tools: readonly string[];
}
export type CapabilityStatus =
  'available' | 'missing_tool' | 'permission_denied';
export function resolveCapabilities(
  manifest: KitManifest,
  actualTools: readonly string[],
  permitted: (tool: string) => boolean,
): ReadonlyArray<{ tool: string; status: CapabilityStatus }> {
  return manifest.tools.map((tool) => ({
    tool,
    status: !actualTools.includes(tool)
      ? 'missing_tool'
      : permitted(tool)
        ? 'available'
        : 'permission_denied',
  }));
}
