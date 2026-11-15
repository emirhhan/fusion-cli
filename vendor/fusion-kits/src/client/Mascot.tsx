import { characterImage } from '../shared/characters';
const STATE_LABELS: Record<string, string> = {
  idle: 'hazır',
  working: 'çalışıyor',
  paused: 'duraklatıldı',
};

export function Mascot({
  state = 'idle',
  small = false,
  identity,
  character,
  name = 'Kit',
  decorative = false,
}: {
  state?: string;
  small?: boolean;
  identity?: string;
  character?: string | null;
  name?: string;
  decorative?: boolean;
}) {
  return (
    <span className={`mascot ${state} ${small ? 'small' : ''}`}>
      <img
        className="dot-body"
        src={characterImage(character, identity)}
        alt={decorative ? '' : `${name}: ${STATE_LABELS[state] ?? state}`}
        width={512}
        height={512}
        draggable={false}
      />
    </span>
  );
}
