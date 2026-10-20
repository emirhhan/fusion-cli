/** Boş değer de başarılı keşiftir; yüklenme ve hata ayrı tutulur. */
export type AsyncState<T> = { status: "loading" } | { status: "ready"; value: T } | { status: "error"; message: string };
