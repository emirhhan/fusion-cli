"""Fusion appserver sürücüsü: bir senaryo = bir süreç, sıralı turlar."""
import json, os, subprocess, sys, threading, time, queue
FUSION = "/Users/motogate/Desktop/all/01-Projeler/fusion-cli/.venv/bin/fusion"

def run(sc, outdir):
    ws = f"/tmp/x/ws_{sc['id']}"
    os.makedirs(ws, exist_ok=True)
    for name, text in sc.get("files", {}).items():
        os.makedirs(os.path.dirname(os.path.join(ws, name)), exist_ok=True); open(os.path.join(ws, name), "w").write(text)
    env = dict(os.environ, FUSION_CONFIG="/tmp/x/cfg.yaml")
    p = subprocess.Popen([FUSION, "app"], cwd=ws, env=env, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    q = queue.Queue()
    threading.Thread(target=lambda: [q.put(l) for l in p.stdout], daemon=True).start()
    def send(o): p.stdin.write(json.dumps(o, ensure_ascii=False) + "\n"); p.stdin.flush()
    log = []; n = 0
    def call(name, data, policy, limit=300):
        nonlocal n; n += 1; rid = f"r{n}"
        send({"tip": "istek", "id": rid, "ad": name, "veri": data})
        end = time.time() + limit; text = []
        while time.time() < end:
            try: line = q.get(timeout=2)
            except queue.Empty: continue
            try: m = json.loads(line)
            except Exception: continue
            tip = m.get("tip")
            if tip == "soru":
                v = m.get("veri", {})
                log.append({"soru": v})
                if v.get("tur") == "onay":
                    ans = {"secim": policy.get("onay", "deny")}
                else:
                    ans = {"metin": policy.get("soru", "")}
                send({"tip": "cevap", "id": m["id"], "veri": ans})
                log.append({"cevap": ans})
            elif tip == "olay":
                v = m.get("veri", {})
                if v.get("tur") in ("arac", "arac_sonuc", "metin", "ilerleme", "durum") or True:
                    log.append({"olay": v})
            elif tip == "sonuc" and m.get("id") == rid:
                log.append({"sonuc": m.get("veri")}); return m.get("veri")
        log.append({"ZAMAN_ASIMI": True}); return None
    call("oturum.baslat", {"kok": ws, "mod": sc.get("mod", "auto"), "kip": sc["kip"]}, {})
    for t in sc["turlar"]:
        log.append({"KULLANICI": t["gorev"]})
        call("tur.calistir", {"gorev": t["gorev"]}, t, limit=sc.get("limit", 240))
    p.stdin.close()
    try: p.wait(10)
    except Exception: p.kill()
    json.dump({"senaryo": sc, "log": log, "stderr": p.stderr.read()[-2000:]},
              open(f"{outdir}/{sc['id']}.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    scs = json.load(open(sys.argv[1])); outdir = sys.argv[2]; os.makedirs(outdir, exist_ok=True)
    only = sys.argv[3:] 
    for sc in scs:
        if only and sc["id"] not in only: continue
        t0 = time.time(); run(sc, outdir); print(sc["id"], round(time.time()-t0), "sn", flush=True)
