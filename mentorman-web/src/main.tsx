import { createRoot } from 'react-dom/client';
import './globals.css';
import { installApiFetch } from './api/client';
import App from './App';
import { initAnalytics } from './lib/analytics';

// Install the /api fetch interceptor before any component mounts.
installApiFetch();
initAnalytics();

createRoot(document.getElementById('root')!).render(<App />);
