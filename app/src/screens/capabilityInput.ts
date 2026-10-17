/**
 * Yazı kutusundaki `/beceri` ve `@mcp` girdilerini çözer.
 *
 * - `/ad` yalnız satırın BAŞINDA ve yalnız o ad bir komut değilse bir beceridir (komut kazanır).
 * - `@ad` metnin herhangi bir yerinde, kelime başında, bilinen ve etkin bir MCP sunucusuysa
 *   o MCP'yi bu tur için seçer. Dosya anmaları (`@src/app.ts`) MCP adı olmadıkça etkilenmez.
 */

export interface CapabilityNames {
  skills: readonly string[];
  mcp: readonly string[];
  /** Bilinen slash komutları: beceri adıyla çakışırsa komut kazanır. */
  commands: readonly string[];
}

export interface CapabilityInput {
  /** Seçilen beceri; `rest` komuttan sonra kalan görev metni. */
  skill: { ad: string; rest: string } | null;
  mcp: string[];
}

const fold = (value: string) => value.toLocaleLowerCase("tr");

export function parseCapabilityInput(text: string, names: CapabilityNames): CapabilityInput {
  let skill: CapabilityInput["skill"] = null;
  const slash = /^\/([^\s/]+)(?:\s+([\s\S]*))?$/.exec(text.trim());
  if (slash) {
    const wanted = fold(slash[1]);
    const isCommand = names.commands.some((command) => fold(command) === wanted);
    const match = isCommand ? undefined : names.skills.find((name) => fold(name) === wanted);
    if (match) skill = { ad: match, rest: (slash[2] ?? "").trim() };
  }
  const mcp: string[] = [];
  for (const found of text.matchAll(/(?:^|\s)@([^\s@]+)/g)) {
    const wanted = fold(found[1].replace(/[.,;:!?)]+$/, ""));
    const match = names.mcp.find((name) => fold(name) === wanted);
    if (match && !mcp.includes(match)) mcp.push(match);
  }
  return { skill, mcp };
}

export const DEFAULT_SKILL_TASK = (skill: string) => `${skill} becerisini bu görev için uygula.`;

/** `/görsel` ve `/gorsel` sohbet içinde görsel üretir; slash komutu değil, normal bir turdur. */
export const isImageCommand = (text: string) => /^\/g[öo]rsel(?:\s|$)/i.test(text.trim());

/** `/görsel` komutundan istem ve en-boy oranı (`--oran 16:9`); oran yoksa 1:1. */
export function parseImageRequest(text: string): { prompt: string; aspect: string } {
  const rest = text.trim().replace(/^\/g[öo]rsel(?:i|ler)?\s*/i, "");
  const option = /(?:^|\s)--(?:oran|aspect)[ =](\d+:\d+)(?=\s|$)/.exec(rest);
  const aspect = option?.[1] ?? "1:1";
  const prompt = (option ? rest.slice(0, option.index) + rest.slice(option.index + option[0].length) : rest)
    .replace(/\s+/g, " ").trim();
  return { prompt, aspect };
}
