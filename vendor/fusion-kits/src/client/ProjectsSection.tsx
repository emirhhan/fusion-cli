import { useEffect, useState } from 'react';
import { FolderPlus, Trash2 } from 'lucide-react';
import { api } from './api';
import { requestFolder, suggestProjectName } from './folder-pick-bridge';

interface ProjectEntry {
  name: string;
  path: string;
  source: 'env' | 'user';
}
interface ProjectList {
  configured: boolean;
  projects: ProjectEntry[];
}

const message = (error: unknown) =>
  error instanceof Error ? error.message : 'İşlem yapılamadı.';

/** Fusion görevlerinin çalışabileceği izinli proje klasörleri. */
export function ProjectsSection() {
  const [list, setList] = useState<ProjectList | null>(null);
  const [name, setName] = useState('');
  const [path, setPath] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const embedded = window.parent !== window;

  const refresh = () =>
    api<ProjectList>('/fusion/projects')
      .then(setList)
      .catch((cause) => setError(message(cause)));
  useEffect(() => {
    void refresh();
  }, []);

  const pick = async () => {
    setError('');
    const chosen = await requestFolder(window, api);
    if (!chosen) return;
    setPath(chosen);
    if (!name.trim()) setName(suggestProjectName(chosen));
  };
  const add = async () => {
    setBusy(true);
    setError('');
    try {
      await api('/fusion/projects', 'POST', {
        name: name.trim(),
        path: path.trim(),
      });
      setName('');
      setPath('');
      await refresh();
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  };
  const remove = async (project: string) => {
    setError('');
    try {
      await api(`/fusion/projects/${encodeURIComponent(project)}`, 'DELETE');
      await refresh();
    } catch (cause) {
      setError(message(cause));
    }
  };

  if (list && !list.configured) return null;
  return (
    <section className="config-note projects" aria-labelledby="projects-title">
      <strong id="projects-title">Projeler</strong>
      <p className="muted">
        Fusion görevleri varsayılan olarak Kits'in kendi çalışma klasöründe
        çalışır. Buraya eklediğin klasörlerde de iş yaptırabilirsin; listede
        olmayan bir klasöre erişilemez.
      </p>
      {list?.projects.length ? (
        <ul className="project-list">
          {list.projects.map((project) => (
            <li key={project.name}>
              <span>
                <b>{project.name}</b>
                <small title={project.path}>{project.path}</small>
              </span>
              {project.source === 'user' ? (
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`${project.name} projesini kaldır`}
                  onClick={() => void remove(project.name)}
                >
                  <Trash2 size={15} />
                </button>
              ) : (
                <small className="muted">sunucu ayarı</small>
              )}
            </li>
          ))}
        </ul>
      ) : (
        list && <p className="muted">Henüz proje eklenmedi.</p>
      )}
      {/* Ayar formunun içinde durur: Enter dış formu (ayarları) göndermesin. */}
      <div
        className="project-add"
        onKeyDown={(event) => {
          if (event.key !== 'Enter') return;
          event.preventDefault();
          if (!busy && name.trim() && path.trim()) void add();
        }}
      >
        <button
          type="button"
          onClick={() => void pick()}
          disabled={!embedded || busy}
          title={
            embedded
              ? undefined
              : 'Klasör seçici yalnız Fusion uygulamasının içinde açılır; yolu elle yazabilirsin.'
          }
        >
          <FolderPlus size={15} /> Klasör seç
        </button>
        <input
          aria-label="Klasör yolu"
          placeholder="/Users/sen/projeler/oyun"
          value={path}
          onChange={(event) => setPath(event.target.value)}
        />
        <input
          aria-label="Proje adı"
          placeholder="Proje adı"
          value={name}
          maxLength={64}
          onChange={(event) => setName(event.target.value)}
        />
        <button
          type="button"
          className="primary"
          disabled={busy || !name.trim() || !path.trim()}
          onClick={() => void add()}
        >
          {busy ? 'Ekleniyor…' : 'Ekle'}
        </button>
      </div>
      {error && (
        <p className="chat-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
