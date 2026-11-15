import type { Conversation } from '../shared/types';
interface Marker {
  version: 1;
  ownerId: string;
  dotId: string;
  requestId: string;
  title: string;
}
interface Options {
  ownerId: string;
  dotId: string;
  title: string;
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
  call: (path: string, method?: string, body?: unknown) => Promise<unknown>;
  createId: () => string;
}
/** Kabul anahtarı, görev gönderilmeden önce kalıcıdır; belirsiz sonuç silinmez. */
export async function createDurableConversation(options: Options) {
  const { storage, ownerId, dotId, call } = options;
  const key = `kits-conversation:${encodeURIComponent(ownerId)}:${encodeURIComponent(dotId)}`;
  const previous = storage.getItem(key);
  const marker: Marker = previous
    ? JSON.parse(previous)
    : {
        version: 1,
        ownerId,
        dotId,
        requestId: options.createId(),
        title: options.title,
      };
  if (
    marker.version !== 1 ||
    marker.ownerId !== ownerId ||
    marker.dotId !== dotId ||
    typeof marker.requestId !== 'string' ||
    !/^[A-Za-z0-9_-]{1,128}$/.test(marker.requestId) ||
    typeof marker.title !== 'string'
  )
    throw new Error('Sohbet kabul kaydı geçersiz; yeni sohbet başlatılmadı.');
  const raw = previous ?? JSON.stringify(marker);
  if (!previous) storage.setItem(key, raw);
  if (storage.getItem(key) !== raw)
    throw new Error('Sohbet kabulü saklanamadı.');
  let recovered = Boolean(previous);
  const read = async (): Promise<Conversation | null> => {
    const receipt = (await call(
      `/conversations/requests/${encodeURIComponent(marker.requestId)}`,
    )) as {
      requestId?: string;
      threadId?: string;
      state?: string;
      conversation?: Conversation;
    };
    if (
      receipt.requestId !== marker.requestId ||
      !['accepted', 'completed'].includes(receipt.state ?? '')
    )
      throw new Error('Sohbet kabul yanıtı geçersiz.');
    if (receipt.state === 'accepted') return null;
    const conversation = receipt.conversation;
    if (
      !conversation ||
      conversation.id !== receipt.threadId ||
      conversation.dotId !== dotId ||
      conversation.ownerId !== ownerId
    )
      throw new Error('Sohbet başka bir kapsama ait.');
    return conversation;
  };
  let conversation: Conversation | null = null;
  if (previous) {
    try {
      conversation = await read();
    } catch (error) {
      if (!(
        error &&
        typeof error === 'object' &&
        'status' in error &&
        error.status === 404
      ))
        throw error;
    }
  }
  if (!conversation) {
    try {
      await call('/conversations', 'POST', {
        dotId,
        title: marker.title,
        requestId: marker.requestId,
      });
    } catch {
      recovered = true;
    }
    conversation = await read();
  }
  if (!conversation)
    throw new Error(
      'Sohbet sonucu henüz doğrulanamadı. Tekrar denediğinde aynı kabul kontrol edilecek.',
    );
  return {
    conversation,
    recovered,
    acknowledge: () => {
      if (storage.getItem(key) !== raw)
        throw new Error('Sohbet kabulü bu sırada değişti.');
      storage.removeItem(key);
      if (storage.getItem(key) !== null)
        throw new Error(
          'Sohbet kabulü temizlenemedi. Görev otomatik gönderilmedi.',
        );
    },
  };
}
