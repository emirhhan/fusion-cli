/**
 * Çevrimdışı Web Audio çözücü (YALNIZ testler için).
 *
 * jsdom'da `OfflineAudioContext` yoktur ve ses çıkışı dinlenemez. Bu dosya,
 * `cues.ts`'in kullandığı düğüm alt kümesini (osilatör, kazanç, çift-ikinci
 * dereceden süzgeç) kaydeder ve Web Audio belirtimindeki formüllerle örnek
 * örnek işler. Böylece `playHum`'ın GERÇEK ürettiği çizge, kulakla değil
 * sayıyla (süre, temel frekans, tını) sınanabilir.
 *
 * Kapsam bilerek dardır: yalnız `playHum`'ın kullandığı özellikler vardır.
 * Başka bir düğüm/parametre kullanılırsa sessizce yok sayılmaz, AÇIKÇA hata verir.
 */

type RampKind = "set" | "linear" | "exponential" | "target";

interface ParamEvent {
  kind: RampKind;
  time: number;
  value: number;
  /** `setTargetAtTime` zaman sabiti. */
  constant?: number;
}

export class FakeParam {
  value: number;
  readonly events: ParamEvent[] = [];
  readonly inputs: FakeNode[] = [];

  constructor(initial: number) {
    this.value = initial;
  }

  setValueAtTime(value: number, time: number): FakeParam {
    this.events.push({ kind: "set", time, value });
    return this;
  }

  linearRampToValueAtTime(value: number, time: number): FakeParam {
    this.events.push({ kind: "linear", time, value });
    return this;
  }

  exponentialRampToValueAtTime(value: number, time: number): FakeParam {
    this.events.push({ kind: "exponential", time, value });
    return this;
  }

  setTargetAtTime(value: number, time: number, constant: number): FakeParam {
    this.events.push({ kind: "target", time, value, constant });
    return this;
  }

  cancelScheduledValues(time: number): FakeParam {
    const kalan = this.events.filter((event) => event.time < time);
    this.events.length = 0;
    this.events.push(...kalan);
    return this;
  }

  /** Otomasyon zaman çizelgesindeki değer (bağlı giriş sinyalleri HARİÇ). */
  at(t: number): number {
    const sirali = [...this.events].sort((a, b) => a.time - b.time);
    let onceki: { time: number; value: number } | null = null;
    for (let i = 0; i < sirali.length; i++) {
      const olay = sirali[i];
      if (olay.kind === "linear" || olay.kind === "exponential") {
        const baslangic = onceki ?? { time: 0, value: this.value };
        if (t < olay.time) {
          const oran = (t - baslangic.time) / (olay.time - baslangic.time);
          if (olay.kind === "linear") return baslangic.value + (olay.value - baslangic.value) * oran;
          return baslangic.value * Math.pow(olay.value / baslangic.value, oran);
        }
        onceki = { time: olay.time, value: olay.value };
      } else if (olay.kind === "target") {
        if (t < olay.time) return onceki?.value ?? this.value;
        const baz = onceki?.value ?? this.value;
        return olay.value + (baz - olay.value) * Math.exp(-(t - olay.time) / (olay.constant ?? 1));
      } else {
        if (t < olay.time) return onceki?.value ?? this.value;
        onceki = { time: olay.time, value: olay.value };
      }
    }
    return onceki?.value ?? this.value;
  }
}

export abstract class FakeNode {
  readonly inputs: FakeNode[] = [];

  connect<T extends FakeNode | FakeParam>(hedef: T): T {
    if (hedef instanceof FakeParam) hedef.inputs.push(this);
    else hedef.inputs.push(this);
    return hedef;
  }
}

export class FakeDestination extends FakeNode {}

export class FakeGain extends FakeNode {
  readonly gain = new FakeParam(1);
}

export class FakeOscillator extends FakeNode {
  type: "sine" | "sawtooth" = "sine";
  readonly frequency = new FakeParam(440);
  readonly detune = new FakeParam(0);
  startAt = Infinity;
  stopAt = Infinity;
  onended: (() => void) | null = null;

  start(time: number): void {
    this.startAt = time;
  }

  stop(time: number): void {
    this.stopAt = time;
  }
}

export class FakeBiquad extends FakeNode {
  type: "lowpass" | "peaking" = "lowpass";
  readonly frequency = new FakeParam(350);
  readonly Q = new FakeParam(1);
  readonly gain = new FakeParam(0);
}

export class FakeContext {
  state = "running";
  currentTime = 0;
  readonly destination = new FakeDestination();
  readonly nodes: FakeNode[] = [];

  resume(): Promise<void> {
    return Promise.resolve();
  }

  private ekle<T extends FakeNode>(dugum: T): T {
    this.nodes.push(dugum);
    return dugum;
  }

  createOscillator(): FakeOscillator {
    return this.ekle(new FakeOscillator());
  }

  createGain(): FakeGain {
    return this.ekle(new FakeGain());
  }

  createBiquadFilter(): FakeBiquad {
    return this.ekle(new FakeBiquad());
  }
}

/** Biquad katsayıları: Web Audio belirtimi (RBJ). `Q` lowpass'ta dB, peaking'te doğrusaldır. */
function biquadKatsayilari(
  tip: "lowpass" | "peaking",
  f0: number,
  q: number,
  gainDb: number,
  hiz: number,
): { b: [number, number, number]; a: [number, number] } {
  const w0 = (2 * Math.PI * f0) / hiz;
  const cos = Math.cos(w0);
  const sin = Math.sin(w0);
  let b0: number;
  let b1: number;
  let b2: number;
  let a0: number;
  let a1: number;
  let a2: number;
  if (tip === "lowpass") {
    const alfa = sin / (2 * Math.pow(10, q / 20));
    b0 = (1 - cos) / 2;
    b1 = 1 - cos;
    b2 = (1 - cos) / 2;
    a0 = 1 + alfa;
    a1 = -2 * cos;
    a2 = 1 - alfa;
  } else {
    const A = Math.pow(10, gainDb / 40);
    const alfa = sin / (2 * q);
    b0 = 1 + alfa * A;
    b1 = -2 * cos;
    b2 = 1 - alfa * A;
    a0 = 1 + alfa / A;
    a1 = -2 * cos;
    a2 = 1 - alfa / A;
  }
  return { b: [b0 / a0, b1 / a0, b2 / a0], a: [a1 / a0, a2 / a0] };
}

/**
 * Çizgeyi `hedef` düğümüne giden sinyal olarak `sure` saniye boyunca işle.
 * Dönen dizi tek kanallı örneklerdir.
 */
export function render(ctx: FakeContext, sure: number, hiz = 16000): Float32Array {
  const adet = Math.round(sure * hiz);
  const cikti = new Float32Array(adet);
  const asamaDurumu = new Map<FakeOscillator, number>();
  const suzgecDurumu = new Map<FakeBiquad, [number, number, number, number]>();
  let onbellek = new Map<FakeNode, number>();
  let t = 0;

  const paramDegeri = (param: FakeParam): number => {
    let toplam = param.at(t);
    for (const giris of param.inputs) toplam += dugumCiktisi(giris);
    return toplam;
  };

  const girisToplami = (dugum: FakeNode): number => {
    let toplam = 0;
    for (const giris of dugum.inputs) toplam += dugumCiktisi(giris);
    return toplam;
  };

  const dugumCiktisi = (dugum: FakeNode): number => {
    const bilinen = onbellek.get(dugum);
    if (bilinen !== undefined) return bilinen;
    let sonuc: number;
    if (dugum instanceof FakeOscillator) {
      if (t < dugum.startAt || t >= dugum.stopAt) {
        sonuc = 0;
      } else {
        const perde = paramDegeri(dugum.frequency) * Math.pow(2, paramDegeri(dugum.detune) / 1200);
        const onceki = asamaDurumu.get(dugum) ?? 0;
        const faz = onceki + perde / hiz;
        asamaDurumu.set(dugum, faz);
        sonuc = dugum.type === "sine" ? Math.sin(2 * Math.PI * faz) : 2 * (faz - Math.floor(faz + 0.5));
      }
    } else if (dugum instanceof FakeGain) {
      sonuc = girisToplami(dugum) * paramDegeri(dugum.gain);
    } else if (dugum instanceof FakeBiquad) {
      const x = girisToplami(dugum);
      const k = biquadKatsayilari(
        dugum.type,
        paramDegeri(dugum.frequency),
        paramDegeri(dugum.Q),
        paramDegeri(dugum.gain),
        hiz,
      );
      const [x1, x2, y1, y2] = suzgecDurumu.get(dugum) ?? [0, 0, 0, 0];
      const y = k.b[0] * x + k.b[1] * x1 + k.b[2] * x2 - k.a[0] * y1 - k.a[1] * y2;
      suzgecDurumu.set(dugum, [x, x1, y, y1]);
      sonuc = y;
    } else {
      throw new Error("offlineAudio: desteklenmeyen düğüm türü");
    }
    onbellek.set(dugum, sonuc);
    return sonuc;
  };

  for (let i = 0; i < adet; i++) {
    t = i / hiz;
    onbellek = new Map();
    cikti[i] = girisToplami(ctx.destination);
  }
  return cikti;
}
