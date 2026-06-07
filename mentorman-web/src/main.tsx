import { createRoot } from 'react-dom/client';
import './globals.css';
import { installApiFetch } from './api/client';
import App from './App';

// Install the /api fetch interceptor before any component mounts.
installApiFetch();

createRoot(document.getElementById('root')!).render(<App />);
