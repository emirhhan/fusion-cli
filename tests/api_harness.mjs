// PWA RPC istemcisi senaryoları; tests/test_remote_pwa_api.py çalıştırır.
import { pathToFileURL } from "node:url";

const dir = process.argv[2];
const { createApi } = await import(pathToFileURL(`${dir}/api.js`).href);
const { importKey } = await import(pathToFileURL(`${dir}/signing.js`).href);
const key = await importKey("00".repeat(32));
const device = { deviceId: "d1", key };
const json = (status, body) => new Response(JSON.stringify(body), { status });
const out = {};

// 1) eşzamanlı çağrılar sırayla gider; sıra numaraları kesin artar, aynı anda tek istek uçuşta
{
  const seqs = [];
  let inflight = 0, max = 0;
  const fetchImpl = async (_url, init) => {
    inflight += 1; max = Math.max(max, inflight);
    seqs.push(Number(init.headers["x-fusion-seq"]));
    await new Promise((r) => setTimeout(r, 5));
    inflight -= 1;
    return json(200, { ok: true });
  };
  const rpc = createApi(device, { fetchImpl });
  await Promise.all(Array.from({ length: 8 }, () => rpc("service.status")));
  out.serial = { max, strictlyIncreasing: seqs.every((v, i) => i === 0 || v > seqs[i - 1]), count: seqs.length };
}

// 2) sira_eski: bir kez yeni sıra ile yeniden dener ve başarır
{
  let calls = 0;
  const fetchImpl = async () => (++calls === 1 ? json(401, { reason: "sira_eski" }) : json(200, { ok: true }));
  const result = await createApi(device, { fetchImpl })("service.status");
  out.retry = { calls, ok: result.ok };
}

// 3) yalnız cihaz_iptal "auth" hatasıdır; imza/saat hataları eşleşmeyi silmez
for (const reason of ["cihaz_iptal", "imza_gecersiz", "zaman_asimi", "sira_eski"]) {
  const fetchImpl = async () => json(401, { reason });
  try {
    await createApi(device, { fetchImpl })("service.status");
    out[reason] = "basarili?";
  } catch (error) {
    out[reason] = { auth: error.auth === true, message: error.message };
  }
}

// 4) bir istek hata verse de kuyruk tıkanmaz
{
  let calls = 0;
  const fetchImpl = async () => { if (++calls === 1) throw new Error("ag"); return json(200, { ok: true }); };
  const rpc = createApi(device, { fetchImpl });
  const first = await rpc("a").catch((e) => e.message);
  const second = await rpc("b");
  out.queue = { first, second: second.ok };
}
// Onay ve sohbet olayları bekleyen arka plan listelerinden önce gider.
{
  const calls = [];
  let release, entered;
  const started = new Promise((resolve) => { entered = resolve; });
  const fetchImpl = async (_url, init) => {
    const payload = JSON.parse(new TextDecoder().decode(init.body));
    calls.push(payload.method);
    if (payload.method === "initial") { entered(); await new Promise((resolve) => { release = resolve; }); }
    return json(200, { ok: true });
  };
  const rpc = createApi(device, { fetchImpl });
  const first = rpc("initial");
  await started;
  const pending = [rpc("projects.list"), rpc("schedules.list"), rpc("approvals.respond"), rpc("tasks.events")];
  release();
  await Promise.all([first, ...pending]);
  out.priority = calls;
}
console.log(JSON.stringify(out));
process.exit(0);
