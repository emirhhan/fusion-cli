// Canlı ekran akışı senaryoları; tests/test_remote_pwa_screen_stream.py çalıştırır.
import { pathToFileURL } from "node:url";
const { createScreenStream, BACKOFF_START_MS, BACKOFF_MAX_MS } = await import(pathToFileURL(process.argv[2]).href);

const FRAME = { ok: true, data: { jpegBase64: "AA==", seq: 1 } };
const NOAPPROVAL = { ok: false, error: "ekran_onay_yok", message: "yok" };
const NONE = { ok: true, data: { state: "none" } };
const ACTIVE = { ok: true, data: { state: "active" } };
const PENDING = { ok: true, data: { state: "pending" } };
const OK = { ok: true, data: { state: "pending" } };

// Betikli sahte RPC: her yöntemin yanıt kuyruğu var; kuyruk bitince `done` çağrılır.
async function run(script, { options = {}, visibleAt = null, startOptions } = {}) {
  const calls = [], states = [], frames = [], sleeps = [];
  let inflight = 0, maxInflight = 0, finish;
  const finished = new Promise((r) => (finish = r));
  const queues = Object.fromEntries(Object.entries(script).map(([k, v]) => [k, [...v]]));
  const rpc = async (method) => {
    inflight += 1; maxInflight = Math.max(maxInflight, inflight);
    await Promise.resolve();
    calls.push(method);
    const queue = queues[method] ?? [];
    const next = queue.length > 1 ? queue.shift() : queue[0];
    inflight -= 1;
    if (queue.length <= 1 && method === "screen.frame" && (queues.__stop?.length ?? 0) === 0) finish();
    if (next instanceof Error) throw next;
    return next;
  };
  let stream;
  stream = createScreenStream({
    rpc,
    onFrame: (data) => frames.push(data),
    onState: (s) => states.push(s),
    sleep: (ms) => { sleeps.push(ms); return new Promise((r) => setTimeout(r, 1)); },
    ...options,
  });
  if (visibleAt === 0) stream.setVisible(false);
  await stream.start(startOptions);
  await Promise.race([finished, new Promise((r) => setTimeout(r, 300))]);
  return { calls, states, frames: frames.length, sleeps, maxInflight, stream };
}

const out = {};
const net = Object.assign(new Error("ağ yok"), {});
const auth = Object.assign(new Error("401"), { auth: true });

// 1) ağ kopar -> üstel bekleme -> kendiliğinden geri gelir
let r = await run({
  "screen.status": [ACTIVE],
  "screen.frame": [FRAME, net, net, net, FRAME, FRAME],
});
r.stream.detach();
out.network = { states: r.states.map((s) => s.state), retries: r.states.filter((s) => s.state === "reconnecting").map((s) => s.retryMs), sleeps: r.sleeps.filter((m) => m >= BACKOFF_START_MS), frames: r.frames, maxInflight: r.maxInflight, cap: BACKOFF_MAX_MS };

// 2) oturum biter -> bir kez kendiliğinden yeniden izin ister -> onay -> akış sürer
r = await run({
  "screen.status": [ACTIVE, NONE, PENDING, ACTIVE],
  "screen.frame": [FRAME, NOAPPROVAL, NOAPPROVAL, FRAME, FRAME],
  "screen.request": [OK],
});
r.stream.detach();
out.expiry = { calls: r.calls, states: r.states.map((s) => s.state), renewed: r.states.some((s) => s.renewed), frames: r.frames };

// 3) kullanıcı durdurur: yenileme istenmez
r = await run({
  "screen.status": [ACTIVE],
  "screen.frame": [FRAME, FRAME],
  "screen.stop": [{ ok: true }],
  __stop: [1],
});
await r.stream.stop();
const callsAfterStop = r.calls.length;
await new Promise((x) => setTimeout(x, 30));
out.stop = { requests: r.calls.filter((c) => c === "screen.request").length, stopCalled: r.calls.includes("screen.stop"), frozen: r.calls.length === callsAfterStop + 0 || r.calls.length <= callsAfterStop + 1 };

// 4) sayfa arka plandayken RPC yapılmaz; görünür olunca sürer
let rpcCount = 0;
const states4 = [];
const s4 = createScreenStream({
  rpc: async (m) => { rpcCount += 1; return m === "screen.status" ? ACTIVE : FRAME; },
  onFrame: () => {}, onState: (s) => states4.push(s.state), sleep: () => new Promise((r) => setTimeout(r, 1)),
});
s4.setVisible(false);
await s4.start();
await new Promise((x) => setTimeout(x, 30));
const whileHidden = rpcCount - 1; // start() içindeki tek screen.status hariç
s4.setVisible(true);
await new Promise((x) => setTimeout(x, 30));
s4.detach();
out.hidden = { whileHidden, afterVisible: rpcCount > 1, paused: states4.includes("paused") };

// 5) kimlik geçersiz: döngü durur, "auth" bildirilir
r = await run({ "screen.status": [ACTIVE], "screen.frame": [auth] });
out.auth = { states: r.states.map((s) => s.state) };

// 6) yenilemeden sonra: etkin oturum varsa istek GÖNDERMEDEN sürdürür; yoksa istemez
r = await run({ "screen.status": [ACTIVE], "screen.frame": [FRAME, FRAME] });
r.stream.detach();
const resumed = r.calls.includes("screen.request");
r = await run({ "screen.status": [NONE], "screen.frame": [FRAME] }, { startOptions: { request: false } });
out.reload = { resumedAsked: resumed, idleAsked: r.calls.includes("screen.request"), idleStates: r.states.map((s) => s.state) };

console.log(JSON.stringify(out));
process.exit(0);
