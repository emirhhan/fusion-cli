/** `/voice` ya da `/dikte` (argümansız ya da `gonder`): masaüstünde mikrofonu açar (P-072). */
export function isDictationCommand(input: string): boolean {
  return /^\/(voice|dikte)(\s+(gonder|gönder|send))?\s*$/i.test(input.trim());
}

/** `/voice gonder`: dikte bitince (kesin metin) taslak kendiliğinden gönderilir. */
export function dictationSendsOnFinal(input: string): boolean {
  return /^\/(voice|dikte)\s+(gonder|gönder|send)\s*$/i.test(input.trim());
}
