import { installSession } from '../../shared/session';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import AuthGate from './components/AuthGate';
import './styles.css';

installSession('family');

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthGate><App /></AuthGate>
  </StrictMode>
);

// 注册 PWA Service Worker（生产环境，HTTPS 或 localhost 下才会注册成功）
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js').catch(() => { });
  });
}
