/** Kurulu SDK signal kabul etmez; süre dolunca sonuç belirsiz kalır, iş tekrarlanmaz. */
const INTELLIGENCE_REQUEST_TIMEOUT_MS = 30000;
export async function boundedIntelligence<T>(
  operation: Promise<T>,
): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      operation,
      new Promise<never>((_, reject) => {
        timer = setTimeout(
          () =>
            reject(
              new Error(
                'Intelligence isteği zaman aşımına uğradı. Aynı sohbeti kurtarmak için yeniden dene.',
              ),
            ),
          INTELLIGENCE_REQUEST_TIMEOUT_MS,
        );
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}
