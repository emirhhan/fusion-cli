import {
  CheckCheck,
  ChevronRight,
  LoaderCircle,
  MessageCircle,
} from 'lucide-react';
import type { Dot, Task } from '../shared/types';
import { Mascot } from './Mascot';
export const relative = (value: number) => {
  const minutes = Math.floor((Date.now() - value) / 60000);
  return minutes < 1
    ? 'Az önce'
    : minutes < 60
      ? `${minutes} dk önce`
      : minutes < 1440
        ? `${Math.floor(minutes / 60)} sa önce`
        : new Date(value).toLocaleDateString('tr-TR');
};
const STATUS_LABELS: Record<string, string> = {
  queued: 'Sırada',
  running: 'Çalışıyor',
  paused: 'Duraklatıldı',
  completed: 'Tamamlandı',
  failed: 'Başarısız',
  cancelled: 'İptal edildi',
};
export const statusLabel = (task: Task) =>
  task.status === 'completed' && task.nextRunAt
    ? 'Planlandı'
    : (STATUS_LABELS[task.status] ?? task.status);
export function Status({ task }: { task: Task }) {
  return (
    <span className={`status ${task.status}`}>
      <span />
      {statusLabel(task)}
    </span>
  );
}

export function TaskRow({
  task,
  onClick,
}: {
  task: Task;
  onClick: () => void;
}) {
  return (
    <button className="task-row" onClick={onClick}>
      <span className="task-row-icon">
        {task.status === 'completed' ? (
          <CheckCheck size={19} />
        ) : task.status === 'running' ? (
          <LoaderCircle className="spin" size={19} />
        ) : (
          <MessageCircle size={19} />
        )}
      </span>
      <div>
        <strong>{task.prompt}</strong>
        <span>
          {task.intervalSeconds
            ? `Her ${task.intervalSeconds < 3600 ? task.intervalSeconds / 60 + ' dk' : task.intervalSeconds / 3600 + ' sa'} bir tekrarlar · `
            : ''}
          {relative(task.updatedAt)}
        </span>
      </div>
      <Status task={task} />
      <ChevronRight size={16} />
    </button>
  );
}
export function Empty({
  title,
  text,
  dot,
}: {
  title: string;
  text: string;
  dot?: Pick<Dot, 'id' | 'character'>;
}) {
  return (
    <div className="large-empty">
      <Mascot identity={dot?.id} character={dot?.character} />
      <h2>{title}</h2>
      <p>{text}</p>
    </div>
  );
}
