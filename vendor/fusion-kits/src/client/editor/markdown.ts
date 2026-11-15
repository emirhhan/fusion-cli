import StarterKit from '@tiptap/starter-kit';
import { MarkdownManager } from '@tiptap/markdown';
import { TableKit } from '@tiptap/extension-table';
import TaskList from '@tiptap/extension-task-list';
import TaskItem from '@tiptap/extension-task-item';
export const documentExtensions = () => [
  StarterKit.configure({
    underline: false,
    link: { openOnClick: false, autolink: false, protocols: ['fusion-asset'] },
    heading: { levels: [1, 2, 3] },
  }),
  TableKit.configure({ table: { resizable: false } }),
  TaskList,
  TaskItem.configure({ nested: true }),
];
export const markdownManager = new MarkdownManager({
  extensions: documentExtensions(),
});
const allowed = new Set([
  'space',
  'code',
  'heading',
  'table',
  'hr',
  'blockquote',
  'list',
  'list_item',
  'paragraph',
  'text',
  'escape',
  'strong',
  'em',
  'codespan',
  'br',
  'del',
  'link',
  'taskList',
  'taskItem',
]);
export function inspectMarkdown(source: string): {
  supported: boolean;
  reason?: string;
} {
  try {
    if (
      /^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/.test(source) ||
      /^\[\^[^\]]+\]:/m.test(source) ||
      /^\s*(\$\$|:::)/m.test(source)
    )
      return {
        supported: false,
        reason:
          'Bu belge genişletilmiş Markdown içeriyor. Kaynak kipi onu aynen korur.',
      };
    const tokens = markdownManager.instance.lexer(source);
    let unsupported = false;
    const pending: unknown[] = [tokens];
    while (pending.length) {
      const value = pending.pop();
      if (!value || typeof value !== 'object') continue;
      if (
        'type' in value &&
        typeof value.type === 'string' &&
        (!allowed.has(value.type) ||
          (value.type === 'heading' &&
            'depth' in value &&
            typeof value.depth === 'number' &&
            value.depth > 3))
      )
        unsupported = true;
      pending.push(...Object.values(value));
    }
    if (unsupported)
      return {
        supported: false,
        reason:
          'Bu belge, Markdown kaynak kipi gerektiren görsel, HTML veya biçimlendirme içeriyor. Hiçbir şey değiştirilmedi.',
      };
    const parsed = markdownManager.parse(source);
    const restored = markdownManager.parse(markdownManager.serialize(parsed));
    if (JSON.stringify(parsed) !== JSON.stringify(restored))
      return {
        supported: false,
        reason:
          'Bazı biçimlendirmeler güvenle dönüştürülemiyor. Kaynak kipi özgün belgeyi bozmadan korur.',
      };
    return { supported: true };
  } catch {
    return {
      supported: false,
      reason: 'Bu Markdown’ın içeriğini korumak için kaynak kipi gerekir.',
    };
  }
}
