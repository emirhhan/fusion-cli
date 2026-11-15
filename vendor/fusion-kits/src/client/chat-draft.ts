/** Thread taslağı ve kaynak seçimi kabulden önce kalıcı tutulur. */
export interface ChatSubmission {
  runId: string;
  text: string;
  source: string;
}
export interface ChatDraft {
  text: string;
  source: string;
  error: string | null;
  submission: ChatSubmission | null;
}
export function loadChatDraft(threadId: string): ChatDraft {
  try {
    const raw = localStorage.getItem(`kits-chat-draft:${threadId}`);
    const value = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
    return {
      text: typeof value.text === 'string' ? value.text : '',
      source: typeof value.source === 'string' ? value.source : '',
      error: null,
      submission:
        value.submission &&
        typeof value.submission === 'object' &&
        typeof (value.submission as ChatSubmission).runId === 'string' &&
        typeof (value.submission as ChatSubmission).text === 'string' &&
        typeof (value.submission as ChatSubmission).source === 'string'
          ? (value.submission as ChatSubmission)
          : null,
    };
  } catch {
    return {
      text: '',
      source: '',
      submission: null,
      error: 'Kayıtlı taslak okunamadı. Tarayıcı depolamasını kontrol et.',
    };
  }
}
export function saveChatDraft(
  threadId: string,
  text: string,
  source: string,
  submission?: ChatSubmission | null,
): string | null {
  try {
    localStorage.setItem(
      `kits-chat-draft:${threadId}`,
      JSON.stringify({
        text,
        source,
        submission:
          submission === undefined
            ? loadChatDraft(threadId).submission
            : submission,
      }),
    );
    return null;
  } catch {
    return 'Taslak saklanamadı. Bu pencereyi kapatmadan metni kopyala.';
  }
}
