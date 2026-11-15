import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { ProjectsSection } from './ProjectsSection';
import { CharacterPicker } from './CharacterPicker';
import { firstUnusedCharacter, resolveCharacter } from '../shared/characters';
import { SLACK_STATUS } from './labels';
import type { Dot, Memory, State, WorkspaceState } from '../shared/types';
export type Dialog =
  | { type: 'space' }
  | { type: 'dot'; dot?: Dot; spaceId: string }
  | { type: 'settings' }
  | { type: 'memory'; memory?: Memory }
  | { type: 'schedule'; threadId: string };
export function WorkspaceDialog({
  dialog,
  state,
  workspace,
  onClose,
  mutate,
}: {
  dialog: Dialog;
  state: State;
  workspace: WorkspaceState;
  onClose: () => void;
  mutate: (path: string, method: string, body?: unknown) => Promise<boolean>;
}) {
  const [name, setName] = useState(
    dialog.type === 'dot' ? (dialog.dot?.name ?? '') : '',
  );
  const [text, setText] = useState(
    dialog.type === 'dot'
      ? (dialog.dot?.instructions ?? '')
      : dialog.type === 'memory'
        ? (dialog.memory?.text ?? '')
        : '',
  );
  const [research, setResearch] = useState(
    dialog.type === 'dot'
      ? (dialog.dot?.researchAllowed ?? true)
      : state.settings.researchAllowed,
  );
  const [memory, setMemory] = useState(
    dialog.type === 'dot'
      ? (dialog.dot?.memoryAllowed ?? true)
      : state.settings.memoryAllowed,
  );
  const [spaceIds, setSpaceIds] = useState(
    dialog.type === 'dot' ? (dialog.dot?.spaceIds ?? [dialog.spaceId]) : [],
  );
  const [defaultSpace, setDefaultSpace] = useState(
    dialog.type === 'dot' ? (dialog.dot?.spaceId ?? dialog.spaceId) : '',
  );
  const [interval, setInterval] = useState('86400');
  const [learningContainer, setLearningContainer] = useState(
    dialog.type === 'dot' ? (dialog.dot?.learningContainerId ?? '') : '',
  );
  const [skillDelivery, setSkillDelivery] = useState(
    dialog.type === 'dot' ? (dialog.dot?.skillDeliveryEnabled ?? false) : false,
  );
  const otherCharacters = workspace.dots
    .filter((item) => dialog.type !== 'dot' || item.id !== dialog.dot?.id)
    .map((item) => resolveCharacter(item.character, item.id));
  const [character, setCharacter] = useState<string>(
    dialog.type === 'dot' && dialog.dot
      ? resolveCharacter(dialog.dot.character, dialog.dot.id)
      : firstUnusedCharacter(otherCharacters),
  );
  const [fusionAllowed, setFusionAllowed] = useState(
    dialog.type === 'dot' ? (dialog.dot?.fusionAllowed ?? false) : false,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const container = useRef<HTMLElement>(null);
  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    container.current
      ?.querySelector<HTMLElement>('input,textarea,select')
      ?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab') {
        const items = [
          ...(container.current?.querySelectorAll<HTMLElement>(
            'button:not([disabled]),input,textarea,select,a[href]',
          ) ?? []),
        ];
        if (event.shiftKey && document.activeElement === items[0]) {
          event.preventDefault();
          items.at(-1)?.focus();
        } else if (!event.shiftKey && document.activeElement === items.at(-1)) {
          event.preventDefault();
          items[0]?.focus();
        }
      }
    };
    document.addEventListener('keydown', key);
    return () => {
      document.removeEventListener('keydown', key);
      previous?.focus();
    };
  }, []);
  const title =
    dialog.type === 'space'
      ? 'Bir şey için bir alan.'
      : dialog.type === 'dot'
        ? dialog.dot
          ? 'Kit ayarları'
          : 'Yeni Kit oluştur'
        : dialog.type === 'settings'
          ? 'Çalışma alanın, kuralların.'
          : dialog.type === 'memory'
            ? 'Hatırlanacak bir şey.'
            : 'Kit görevi planla';
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section
        className="modal"
        data-dialog-kind={dialog.type}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        ref={container}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          className="modal-close icon-button"
          aria-label="Pencereyi kapat"
          onClick={onClose}
        >
          <X size={18} />
        </button>
        <span className="eyebrow">FUSION KITS</span>
        <h2 id="dialog-title">{title}</h2>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError('');
            let path = '',
              method = 'POST',
              body: unknown;
            if (dialog.type === 'space') {
              path = '/spaces';
              body = { name, description: text };
            }
            if (dialog.type === 'dot') {
              path = dialog.dot ? `/dots/${dialog.dot.id}` : '/dots';
              method = dialog.dot ? 'PUT' : 'POST';
              body = {
                spaceId: defaultSpace,
                spaceIds,
                name,
                instructions: text,
                researchAllowed: research,
                memoryAllowed: memory,
                fusionAllowed,
                character,
                learningContainerId: learningContainer.trim() || null,
                skillDeliveryEnabled: skillDelivery,
              };
            }
            if (dialog.type === 'settings') {
              path = '/settings';
              method = 'PATCH';
              body = { researchAllowed: research, memoryAllowed: memory };
            }
            if (dialog.type === 'memory') {
              path = dialog.memory
                ? `/memories/${dialog.memory.id}`
                : '/memories';
              method = dialog.memory ? 'PUT' : 'POST';
              body = { text };
            }
            if (dialog.type === 'schedule') {
              path = '/tasks';
              body = {
                prompt: text,
                threadId: dialog.threadId,
                intervalSeconds: Number(interval),
              };
            }
            if (await mutate(path, method, body)) onClose();
            else
              setError(
                'Kaydedilemedi. Çalışma alanı hatasını inceleyip yeniden dene.',
              );
            setBusy(false);
          }}
        >
          {dialog.type === 'dot' && (
            <CharacterPicker
              value={character}
              used={otherCharacters}
              onChange={setCharacter}
            />
          )}
          {(dialog.type === 'space' || dialog.type === 'dot') && (
            <>
              <label className="field-label" htmlFor="entity-name">
                Ad
              </label>
              <input
                id="entity-name"
                value={name}
                maxLength={40}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </>
          )}
          {dialog.type !== 'settings' && (
            <>
              <label className="field-label" htmlFor="entity-text">
                {dialog.type === 'dot'
                  ? 'Rol yönergeleri'
                  : dialog.type === 'space'
                    ? 'Buraya ne ait?'
                    : dialog.type === 'memory'
                      ? 'Tercih veya bağlam'
                      : 'Yeniden ele alınacak görev'}
              </label>
              <textarea
                id="entity-text"
                rows={4}
                maxLength={dialog.type === 'schedule' ? 4000 : 2000}
                required={dialog.type !== 'space'}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={
                  dialog.type === 'dot'
                    ? 'Özenli bir araştırma ortağısın. Kanıtları karşılaştır ve belirsizlik konusunda net ol.'
                    : ''
                }
              />
            </>
          )}
          {dialog.type === 'dot' && (
            <label className="permission-row">
              <input
                type="checkbox"
                checked={fusionAllowed}
                onChange={(event) => setFusionAllowed(event.target.checked)}
              />
              <span>
                <strong>Fusion görevleri</strong>
                <small>
                  Yapılandırılmış yerel proje kökünde Fusion çekirdeğiyle
                  çalışır. Kit bilgisayarının izinlerinden ayrıdır; varsayılan
                  kapalıdır.
                </small>
              </span>
            </label>
          )}
          {dialog.type === 'dot' && (
            <fieldset className="space-access-fields">
              <legend>Alan erişimi</legend>
              <p className="muted">
                Bu Kit’in sayfaları nerede okuyup düzenleyebileceğini seç.
              </p>
              {workspace.spaces.map((space) => (
                <label className="permission-row" key={space.id}>
                  <input
                    type="checkbox"
                    checked={spaceIds.includes(space.id)}
                    onChange={(event) => {
                      const next = event.target.checked
                        ? [...spaceIds, space.id]
                        : spaceIds.filter((id) => id !== space.id);
                      setSpaceIds(next);
                      if (!next.includes(defaultSpace))
                        setDefaultSpace(next[0] ?? '');
                    }}
                  />
                  <span>{space.name}</span>
                </label>
              ))}
              <label className="field-label" htmlFor="default-space">
                Kaydedilen sayfalar için varsayılan hedef
              </label>
              <select
                id="default-space"
                value={defaultSpace}
                required
                onChange={(event) => setDefaultSpace(event.target.value)}
              >
                <option value="" disabled>
                  Bir Alan seç
                </option>
                {workspace.spaces
                  .filter((space) => spaceIds.includes(space.id))
                  .map((space) => (
                    <option key={space.id} value={space.id}>
                      {space.name}
                    </option>
                  ))}
              </select>
            </fieldset>
          )}
          {(dialog.type === 'dot' || dialog.type === 'settings') && (
            <>
              <label className="permission-row">
                <input
                  type="checkbox"
                  checked={research}
                  onChange={(e) => setResearch(e.target.checked)}
                />
                <span>
                  <strong>Herkese açık sayfa araştırması</strong>
                  <small>
                    Sunucu tarafındaki salt okunur tarayıcı aracına izin ver.
                    Genel ayarlar her zaman önceliklidir.
                  </small>
                </span>
              </label>
              <label className="permission-row">
                <input
                  type="checkbox"
                  checked={memory}
                  onChange={(e) => setMemory(e.target.checked)}
                />
                <span>
                  <strong>Kayıtlı bellekleri kullan</strong>
                  <small>
                    Tercihlerini yeni turlara dahil et. İzni değiştirmek çalışan
                    işleri durdurur.
                  </small>
                </span>
              </label>
            </>
          )}
          {dialog.type === 'dot' &&
            workspace.setup.conversationStore === 'local' && (
              <div className="config-note">
                <strong>Otomatik öğrenme</strong>
                <p>
                  Sohbetler bu bilgisayarda tutuluyor. Otomatik öğrenme ve
                  yayımlanmış beceri teslimi harici öğrenme hizmeti gerektirir;
                  yerel kipte kapalıdır.
                </p>
              </div>
            )}
          {dialog.type === 'dot' &&
            workspace.setup.conversationStore !== 'local' && (
              <fieldset className="space-access-fields">
                <legend>Otomatik öğrenme</legend>
                <label className="field-label" htmlFor="learning-container">
                  Öğrenme kapsayıcı kimliği
                </label>
                <input
                  id="learning-container"
                  value={learningContainer}
                  maxLength={64}
                  pattern="[a-z0-9]+(-[a-z0-9]+)*"
                  placeholder="research-workflow"
                  aria-describedby="learning-help"
                  onChange={(event) => {
                    setLearningContainer(event.target.value);
                    if (!event.target.value.trim()) setSkillDelivery(false);
                  }}
                />
                <p className="muted" id="learning-help">
                  Bu kapsayıcıyı önce Intelligence projende oluştur. Yeni
                  sohbetler buna kanıt ekler. Yeni sohbetleri öğrenmenin dışında
                  tutmak için boş bırak. Mevcut sohbetler özgün atamasını korur.
                </p>
                <label className="permission-row">
                  <input
                    type="checkbox"
                    checked={skillDelivery}
                    disabled={!learningContainer.trim()}
                    onChange={(event) => setSkillDelivery(event.target.checked)}
                  />
                  <span>
                    <strong>Yayımlanmış becerileri kullan</strong>
                    <small>
                      Her sohbetin atanmış kapsayıcısından gözden geçirilmiş
                      becerileri yükle. Teslimi bağlı öğrenme hizmetinde de
                      etkinleştir. Bunu kapatmak beceri yüklemeyi durdurur;
                      kanıt toplamayı durdurmaz.
                    </small>
                  </span>
                </label>
                <p>
                  Öğrenme hizmetinin bağlantı ve beceri ayarlarını bağlı hesap
                  üzerinden yönetebilirsin.
                </p>
              </fieldset>
            )}
          {dialog.type === 'schedule' && (
            <>
              <label className="field-label" htmlFor="schedule-interval">
                Her başarılı çalıştırmadan sonra tekrarla
              </label>
              <select
                id="schedule-interval"
                value={interval}
                onChange={(e) => setInterval(e.target.value)}
              >
                <option value="60">Her dakika (deneme)</option>
                <option value="3600">Her saat</option>
                <option value="86400">Her gün</option>
                <option value="604800">Her hafta</option>
              </select>
              <p className="muted">
                Sekme kapalıyken bile sunucuda bu sohbetin içinde çalışır.
                Başarısız çalıştırmalar elle yeniden denemeyi bekler.
              </p>
            </>
          )}
          {dialog.type === 'settings' && (
            <div className="config-note">
              <strong>Hizmet kurulumu</strong>
              <p>
                {workspace.setup.missing.length
                  ? `${workspace.setup.missing.join(', ')} değerlerini sunucu ortamına ekle, ardından yeniden başlat.`
                  : 'Metin yapılandırması mevcut. Başarılı bir sohbet bağlantıyı doğrular.'}
              </p>
              <p>
                Sohbet deposu:{' '}
                {workspace.setup.conversationStore === 'local'
                  ? 'bu bilgisayar (yerel dosya). Slack kanalı ve otomatik öğrenme bu kipte kullanılamaz.'
                  : workspace.setup.conversationStore === 'intelligence'
                    ? 'bağlı harici sohbet deposu.'
                    : 'yapılandırılmadı.'}
              </p>
              <p>
                Slack:{' '}
                {SLACK_STATUS[workspace.setup.slack] ?? workspace.setup.slack}.
                Ses:{' '}
                {workspace.setup.voiceRealtime
                  ? 'OpenAI Realtime (isteğe bağlı anahtar tanımlı)'
                  : workspace.setup.voice
                    ? 'yerel ve ücretsiz (Fusion içinde Mac’in kendi tanıması ve sesi; tarayıcıda tarayıcının sesi)'
                    : 'sohbet kurulumu bitince açılır'}
                .
              </p>
              <p>
                Fusion sağlayıcılarını ana uygulamanın Ayarlar ve bağlantılar
                bölümünden yönet.
              </p>
            </div>
          )}
          {dialog.type === 'settings' && <ProjectsSection />}
          {dialog.type === 'memory' && (
            <p className="muted">
              Bellekler açıkça belirtilen tercihlerdir, otomatik öğrenme
              değildir. Gizli bilgi yazma; etkin bellekler model sağlayıcına
              gönderilir.
            </p>
          )}
          {error && (
            <p className="chat-error" role="alert">
              {error}
            </p>
          )}
          <button className="primary full" disabled={busy}>
            {busy ? 'Kaydediliyor…' : 'Kaydet'}
          </button>
        </form>
      </section>
    </div>
  );
}
