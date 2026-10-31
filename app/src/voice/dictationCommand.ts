/** `/voice` ya da `/dikte` (argümansız ya da `gonder`): masaüstünde mikrofonu açar (P-072). */
export function isDictationCommand(input: string): boolean {
  return /^\/(voice|dikte)(\s+(gonder|gönder|send))?\s*$/i.test(input.trim());
}
