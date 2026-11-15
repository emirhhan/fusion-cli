import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './style.css';
import './editor.css';
import './brand/fonts.css';
import './kits.css';
import './kits-dark.generated.css';
import './fusion-brand.generated.css';
import { applyHostTheme, listenHostTheme } from './host-theme';
applyHostTheme(new URLSearchParams(location.search).get('theme'));
listenHostTheme(window);
if (new URLSearchParams(location.search).get('surface') === 'kits') {
  document.documentElement.dataset.fusionSurface = 'kits';
}
createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
