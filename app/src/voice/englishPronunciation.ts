// Derived from Carnegie Mellon University's CMUdict, revision 74790861.
// The redistribution license ships in public/licenses/cmudict.txt.
import englishLexicon from "./talk-english.tsv?raw";

const productPronunciations = new Map([
  ["agentic", "acentik"], ["agentics", "acentiks"],
  ["agent", "eycınt"], ["agents", "eycınts"],
  ["workflow", "vörkflo"], ["workflows", "vörkflouz"],
  ["benchmark", "bençmark"], ["benchmarks", "bençmarks"],
  ["backend", "bekend"], ["frontend", "front end"],
  ["dashboard", "deşbord"], ["dataset", "deyta set"],
  ["database", "deyta beys"], ["data warehouse", "deyta verhaus"],
  ["framework", "freymvörk"], ["deployment", "diploymınt"],
  ["embedding", "embeding"], ["embeddings", "embedingz"],
  ["prompt", "prompt"], ["prompts", "prompts"], ["inference", "inferıns"],
  ["browser", "bravzır"], ["buffer", "bafır"], ["tokenization", "tokınızeyşın"],
  ["token", "tokın"], ["tokens", "tokınz"], ["chunk", "çank"],
  ["fine-tuned", "fayn tünd"], ["fine-tune", "fayn tün"], ["grounding", "graunding"],
  ["load balancer", "loud balansır"], ["container", "kınteynır"],
  ["speech recognition", "spiç rekıgnişın"], ["barge-in", "barc in"],
  ["open source", "opın sors"], ["repository", "rıpozıtori"],
  ["version control", "vörjın kontrol"], ["checkpoint", "çekpoint"],
  ["fine tuning", "fayn tüning"], ["fine-tuning", "fayn tüning"],
  ["pipeline", "payplayn"], ["multimodal", "maltimodal"],
  ["fallback", "folbek"], ["feature", "fiçır"], ["features", "fiçırz"],
  ["cache", "keş"], ["cached", "keşt"], ["caching", "keşing"],
  ["endpoint", "endpoint"], ["webhook", "vebhuk"], ["localhost", "lokılhost"],
  ["serverless", "sörvırlıs"], ["runtime", "rantaym"], ["sandbox", "sendboks"],
  ["latency", "leytınsi"], ["throughput", "truput"],
  ["middleware", "midılver"], ["microservice", "maykro sörvis"],
  ["release", "rilis"], ["rollback", "rolbek"], ["pull request", "pul rikvest"],
  ["code review", "kod rivyu"], ["commit", "komit"], ["branch", "brenç"],
  ["merge", "mörc"], ["push", "puş"], ["pull", "pul"],
  ["devops", "devops"], ["kubernetes", "kubernetiz"],
  ["postgresql", "postgres kyu el"], ["postgres", "postgres"],
  ["sqlite", "es kyu el layt"], ["node.js", "nod cey es"],
  ["react", "riekt"], ["next.js", "nekst cey es"], ["vue", "vyu"],
  ["swift", "svift"], ["rust", "rast"], ["java", "cava"],
  ["linux", "linuks"], ["chrome", "krom"], ["safari", "safari"],
  ["vercel", "vörsel"], ["cloudflare", "klaudfler"], ["firebase", "fayırbeys"],
  ["supabase", "supabeys"], ["redis", "redis"],
  ["claude", "klod"], ["gemini", "ceminay"], ["codex", "kodeks"],
  ["hugging face", "haging feys"], ["nemotron", "nemotron"],
  ["lightning", "laytning"], ["realtime", "riıl taym"], ["real-time", "riıl taym"],
  ["heygen", "heycın"], ["elevenlabs", "ilevın lebz"],
  ["typescript", "tayp skript"], ["websocket", "veb sokıt"],
  ["chromium", "kromiyum"], ["chromadb", "kroma di bi"], ["litellm", "layt el el em"],
  ["online", "onlayn"], ["offline", "oflayn"], ["feedback", "fidbek"],
  ["marketing", "marketing"], ["remarketing", "ri marketing"],
  ["retargeting", "ritargıting"], ["e-commerce", "i komırs"],
  ["meta ads", "meta edz"], ["advantage+", "edvantıc plas"],
  ["conversion", "kınvörjın"], ["conversions", "kınvörjınz"],
  ["attribution", "etribyuşın"], ["pixel", "piksıl"], ["tracking", "treking"],
  ["machine learning", "maşin lörning"], ["deep learning", "dip lörning"],
  ["speech to text", "spiç tu tekst"], ["text to speech", "tekst tu spiç"],
]);

const turkishOverlap = new Set([
  "ana", "bir", "bu", "ve", "ile", "de", "da", "can", "test", "market", "proje", "model", "panel", "program", "plan", "ring",
  "miting", "doping", "kamping", "brifing", "rating", "holding", "renting", "puding",
  "kasting", "marketing", "mobbing", "banking", "rest", "safari",
]);
const englishShape = /[wqx]|(?:tion|sion|ture|ough|eigh|ing|ous|cious|sive|ible|cial|dge|ment|less|ness|ful|ward|wards|ship|eer|isms?)$/u;
const turkishLetters = /[çğıöşüÇĞİÖŞÜ]/u;
const englishFunctionWords = new Set(["the", "this", "these", "those", "with", "from", "into", "after", "before"]);
const phraseToken = /[a-z]+/giu;
const suffixes = "['’‘ʼ]([\\p{L}]+)";
const boundaries = "(?<![\\p{L}\\p{N}])";
const endBoundary = "(?![\\p{L}\\p{N}])";
const productPattern = new RegExp(boundaries + "(" + [...productPronunciations.keys()]
  .sort((a, b) => b.length - a.length)
  .map(name => name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/ /g, "[ \\t]+"))
  .join("|") + ")(?:" + suffixes + ")?" + endBoundary, "giu");
const wordPattern = new RegExp(boundaries + "(\\p{L}+)(?:" + suffixes + ")?" + endBoundary, "gu");

function dictionaryPronunciation(word: string): string | undefined {
  // The generated entries are sorted. Search the raw table without allocating
  // 113,000 Map entries at the first spoken word.
  let first = 0;
  let end = englishLexicon.length;
  while (first < end) {
    const middle = Math.floor((first + end) / 2);
    const line = englishLexicon.lastIndexOf("\n", middle - 1) + 1;
    const next = englishLexicon.indexOf("\n", middle);
    const tab = englishLexicon.indexOf("\t", line);
    const key = englishLexicon.slice(line, tab);
    if (key === word) return englishLexicon.slice(tab + 1, next);
    if (key < word) first = next + 1;
    else end = line;
  }
  return undefined;
}

function suffixOn(spoken: string, suffix?: string): string {
  if (!suffix) return spoken;
  const original = suffix.toLocaleLowerCase("tr");
  const vowels = spoken.toLocaleLowerCase("tr").match(/[aeıioöuü]/gu);
  const lastVowel = vowels?.[vowels.length - 1];
  if (!lastVowel) return spoken + original;
  const endsWithVowel = /[aeıioöuü]$/iu.test(spoken);
  const front = "eiöü".includes(lastVowel);
  const high = "ou".includes(lastVowel) ? "u" : "öü".includes(lastVowel) ? "ü" : front ? "i" : "ı";
  const low = front ? "e" : "a";
  if (/^[ny]?[ıiuü]n$/u.test(original)) return spoken + (endsWithVowel ? "n" : "") + high + "n";
  if (/^[sy]?[ıiuü]$/u.test(original)) {
    const buffer = original.startsWith("s") ? "s" : "y";
    return spoken + (endsWithVowel ? buffer : "") + high;
  }
  if (/^y?[ae]$/u.test(original)) return spoken + (endsWithVowel ? "y" : "") + low;
  return spoken + original;
}

function originalCase(source: string, spoken: string): string {
  return /^[A-Z]/u.test(source)
    ? spoken[0].toLocaleUpperCase("tr") + spoken.slice(1)
    : spoken;
}

export function pronounceEnglishInTurkish(text: string): string {
  // Apply the dictionary only with English spelling clues or in a clear English phrase.
  // Names and shared words such as “Can”, “test”, “market” stay in Turkish outside those phrases.
  const englishPhrases = [...text.matchAll(/[^.!?;,\n]+/gu)].filter(part => {
    const words = part[0].match(phraseToken) ?? [];
    return words.filter(word => englishFunctionWords.has(word.toLowerCase())).length >= 2;
  });
  const read = (spoken: string, word: string, suffix?: string) => originalCase(word, suffixOn(spoken, suffix));

  // Scan both patterns on the original string. Phonetic replacements must not be looked up again.
  const products = new Map<number, { end: number; spoken: string }>();
  for (const match of text.matchAll(productPattern)) {
    const word = match[1];
    const spoken = productPronunciations.get(word.toLowerCase().replace(/[ \t]+/gu, " "));
    if (spoken) products.set(match.index, { end: match.index + match[0].length, spoken: read(spoken, word, match[2]) });
  }

  let cursor = 0;
  let result = "";
  for (const match of text.matchAll(wordPattern)) {
    const index = match.index;
    if (index < cursor) continue;
    const product = products.get(index);
    if (product) {
      result += text.slice(cursor, index) + product.spoken;
      cursor = product.end;
      continue;
    }
    const word = match[1];
    const lower = word.toLowerCase();
    if (word.length < 3 || turkishLetters.test(word) || /^[A-Z]+$/u.test(word) || turkishOverlap.has(lower)) continue;
    const end = index + match[0].length;
    // Capitalized names can belong to other languages. Product overrides above
    // cover names whose pronunciation is known.
    if (/^[A-Z]/u.test(word) && !englishFunctionWords.has(lower)) continue;
    if (!englishShape.test(lower) && !englishFunctionWords.has(lower)
      && !englishPhrases.some(phrase => index >= phrase.index && end <= phrase.index + phrase[0].length)) continue;
    const spoken = dictionaryPronunciation(lower);
    if (!spoken) continue;
    result += text.slice(cursor, index) + read(spoken, word, match[2]);
    cursor = end;
  }
  return result + text.slice(cursor);
}
