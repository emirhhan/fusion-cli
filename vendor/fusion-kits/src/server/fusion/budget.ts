/** İnsan kararında durabilen compute süresi; kapanışta zamanlayıcı temizlenir. */
export class ComputeBudget {
  private remaining: number;
  private started = 0;
  private timer?: ReturnType<typeof setTimeout>;
  private closed = false;
  constructor(
    durationMs: number,
    private expired: () => void,
  ) {
    this.remaining = durationMs;
    this.resume();
  }
  pause() {
    if (!this.timer) return;
    clearTimeout(this.timer);
    this.timer = undefined;
    this.remaining -= Date.now() - this.started;
  }
  resume() {
    if (this.closed || this.timer) return;
    this.started = Date.now();
    this.timer = setTimeout(
      () => {
        this.timer = undefined;
        this.closed = true;
        this.expired();
      },
      Math.max(0, this.remaining),
    );
  }
  close() {
    this.pause();
    this.closed = true;
  }
}
