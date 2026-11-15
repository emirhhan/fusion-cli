export function parseColor(
  token: string,
): { r: number; g: number; b: number; a: number } | null;
export function darkColor(token: string): string;
export function darkValue(property: string, value: string): string;
export function darkStylesheet(css: string): string;
