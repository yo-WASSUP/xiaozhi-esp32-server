import { installSession } from '../../shared/session';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import AuthGate from './components/AuthGate';
import './styles.css';

installSession('patient');

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthGate><App /></AuthGate>
  </StrictMode>
);

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js').catch(() => { });
  });
}
