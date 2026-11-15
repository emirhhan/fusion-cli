/** Keeps asynchronous chat setup tied to the page and specialist that requested it. */
export class PageChatRequests {
  private scope = '';
  private generation = 0;
  select(scope: string) {
    if (scope !== this.scope) {
      this.scope = scope;
      this.generation++;
    }
  }
  async run<T>(
    scope: string,
    load: () => Promise<T>,
    callbacks: {
      success: (value: T) => void;
      failure: (error: unknown) => void;
      settled: () => void;
    },
  ) {
    if (scope !== this.scope) return;
    const generation = ++this.generation;
    const current = () =>
      this.scope === scope && this.generation === generation;
    try {
      const value = await load();
      if (current()) callbacks.success(value);
    } catch (error) {
      if (current()) callbacks.failure(error);
    } finally {
      if (current()) callbacks.settled();
    }
  }
}
