import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { Logo } from './Logo';
afterEach(cleanup);
it('kullanıcının yeni F kaynağını kullanır ve erişilebilir adı korur', () => {
  render(<Logo size={32} title='Fusion' />);
  const image = screen.getByRole('img', { name: 'Fusion' });
  expect(image.getAttribute('src')).toContain('fusion-mark.svg');
  expect(image.getAttribute('width')).toBe('32');
});
