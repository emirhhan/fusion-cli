import { useEffect, useRef } from 'react';
import { EditorContent, useEditor, useEditorState } from '@tiptap/react';
import { Markdown } from '@tiptap/markdown';
import Placeholder from '@tiptap/extension-placeholder';
import {
  Bold,
  Italic,
  List,
  ListOrdered,
  Quote,
  Code2,
  Undo2,
  Redo2,
  Link2,
} from 'lucide-react';
import { documentExtensions } from './markdown';
import { SlashCommands } from './slash-commands';
import { openPageLink } from '../page-navigation';
export default function RichEditor({
  value,
  onChange,
  onNotice,
}: {
  value: string;
  onChange: (value: string) => void;
  onNotice: (message: string) => void;
}) {
  const change = useRef(onChange);
  change.current = onChange;
  const notice = useRef(onNotice);
  notice.current = onNotice;
  const emitted = useRef(value);
  const editor = useEditor({
    extensions: [
      ...documentExtensions(),
      Markdown,
      Placeholder.configure({
        placeholder: 'Yazmaya başla veya bloklar için / yaz…',
      }),
      SlashCommands,
    ],
    content: value,
    contentType: 'markdown',
    immediatelyRender: false,
    editorProps: {
      attributes: {
        class: 'document-prose',
        'aria-label': 'Sayfa içeriği',
        role: 'textbox',
        'aria-multiline': 'true',
      },
      handleClick: (_view, _pos, event) => {
        const target =
          event.target instanceof Element ? event.target.closest('a') : null;
        const href = target?.getAttribute('href');
        if (href?.startsWith('fusion-asset:')) {
          event.preventDefault();
          const id = href.slice('fusion-asset:'.length);
          const card = target
            ?.closest('.document-reading-column')
            ?.querySelector<HTMLElement>(`[data-asset-id="${CSS.escape(id)}"]`);
          card?.scrollIntoView({ block: 'nearest' });
          card?.focus();
          notice.current(
            card
              ? 'Dosyanın önizlemesi belge eklerinde gösterilir.'
              : 'Dosya kimliği korunuyor; bu belgenin ilk 8 eki için önizleme gösteriliyor.',
          );
          return true;
        }
        if (
          href?.startsWith('/#/spaces/') &&
          (event.metaKey || event.ctrlKey)
        ) {
          event.preventDefault();
          openPageLink(href);
          return true;
        }
        return false;
      },
      handlePaste: (_view, event) => {
        const html = event.clipboardData?.getData('text/html') ?? '';
        if (/<(img|iframe|script)\b/i.test(html)) {
          event.preventDefault();
          notice.current(
            'Görseller ve gömülü içerik burada desteklenmez. Özgün işaretlemeyi korumak için Markdown kaynağını kullan.',
          );
          return true;
        }
        return false;
      },
    },
    onUpdate: ({ editor }) => {
      const markdown = editor.getMarkdown();
      emitted.current = markdown;
      change.current(markdown);
    },
  });
  const state = useEditorState({
    editor,
    selector: ({ editor }) =>
      editor
        ? {
            bold: editor.isActive('bold'),
            italic: editor.isActive('italic'),
            bullet: editor.isActive('bulletList'),
            ordered: editor.isActive('orderedList'),
            quote: editor.isActive('blockquote'),
            code: editor.isActive('codeBlock'),
            undo: editor.can().undo(),
            redo: editor.can().redo(),
          }
        : null,
  });
  useEffect(() => {
    if (editor && value !== emitted.current) {
      emitted.current = value;
      editor.commands.setContent(value, {
        contentType: 'markdown',
        emitUpdate: false,
      });
    }
  }, [editor, value]);
  if (!editor)
    return <div className="editor-loading">Düzenleyici yükleniyor…</div>;
  return (
    <>
      <div
        className="format-toolbar"
        role="toolbar"
        aria-label="Metin biçimlendirme"
      >
        <button
          title="Kalın (⌘/Ctrl B)"
          aria-label="Kalın"
          aria-pressed={state?.bold}
          onClick={() => editor.chain().focus().toggleBold().run()}
        >
          <Bold size={16} />
        </button>
        <button
          title="İtalik (⌘/Ctrl I)"
          aria-label="İtalik"
          aria-pressed={state?.italic}
          onClick={() => editor.chain().focus().toggleItalic().run()}
        >
          <Italic size={16} />
        </button>
        <span className="toolbar-divider" />
        <button
          title="Madde işaretli liste"
          aria-label="Madde işaretli liste"
          aria-pressed={state?.bullet}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
        >
          <List size={17} />
        </button>
        <button
          title="Numaralı liste"
          aria-label="Numaralı liste"
          aria-pressed={state?.ordered}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
        >
          <ListOrdered size={17} />
        </button>
        <button
          title="Alıntı"
          aria-label="Alıntı"
          aria-pressed={state?.quote}
          onClick={() => editor.chain().focus().toggleBlockquote().run()}
        >
          <Quote size={15} />
        </button>
        <button
          title="Kod bloğu"
          aria-label="Kod bloğu"
          aria-pressed={state?.code}
          onClick={() => editor.chain().focus().toggleCodeBlock().run()}
        >
          <Code2 size={17} />
        </button>
        <button
          title="Bağlantı ekle"
          aria-label="Bağlantı ekle"
          onClick={() => {
            const url = window.prompt(
              'Bağlantı adresi (https:// veya dahili sayfa bağlantısı)',
              editor.getAttributes('link').href ?? '',
            );
            if (url === null) return;
            if (!url) {
              editor.chain().focus().unsetLink().run();
              return;
            }
            if (!/^(https?:\/\/|\/#\/spaces\/)/i.test(url)) {
              onNotice(
                'Herkese açık bir http(s) adresi veya dahili sayfa bağlantısı kullan.',
              );
              return;
            }
            editor
              .chain()
              .focus()
              .extendMarkRange('link')
              .setLink({ href: url })
              .run();
          }}
        >
          <Link2 size={16} />
        </button>
        <span className="toolbar-divider" />
        <button
          aria-label="Geri al"
          title="Geri al"
          disabled={!state?.undo}
          onClick={() => editor.chain().focus().undo().run()}
        >
          <Undo2 size={16} />
        </button>
        <button
          aria-label="Yinele"
          title="Yinele"
          disabled={!state?.redo}
          onClick={() => editor.chain().focus().redo().run()}
        >
          <Redo2 size={16} />
        </button>
      </div>
      <EditorContent editor={editor} />
      <p className="editor-hint">
        Bloklar için <kbd>/</kbd> yaz · Kaydetmek için ⌘/Ctrl + S
      </p>
    </>
  );
}
