import { afterEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import App from './App';

afterEach(() => vi.unstubAllGlobals());

it('keeps operational panels and the existing conversation accessible before telemetry responds', () => {
  vi.stubGlobal('window', {
    localStorage: { getItem: (key: string) => key === 'creation_access_token' ? 'access' : 'conversation' },
    sessionStorage: { getItem: () => null },
  });
  const html = renderToStaticMarkup(<App />);
  expect(html).toContain('id="system-vitals"');
  expect(html).toContain('Verificar laboratório');
  expect(html).toContain('Criar missão');
  const input = html.match(/<textarea[^>]*aria-label="Message DEUS"[^>]*>/)?.[0];
  expect(input).toBeDefined();
  expect(input).not.toContain('disabled');
});
