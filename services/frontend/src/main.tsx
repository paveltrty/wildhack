import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Network from './pages/Network';
import Orders from './pages/Orders';
import Vehicles from './pages/Vehicles';
import Analytics from './pages/Analytics';
import Settings from './pages/Settings';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: 1 },
  },
});

const navStyle: React.CSSProperties = {
  display: 'flex',
  gap: '0',
  padding: '0 24px',
  background: '#161b22',
  borderBottom: '1px solid #30363d',
  position: 'sticky',
  top: 0,
  zIndex: 100,
};

const linkBase: React.CSSProperties = {
  padding: '14px 20px',
  textDecoration: 'none',
  color: '#8b949e',
  fontSize: '14px',
  fontWeight: 500,
  borderBottom: '2px solid transparent',
  transition: 'color 0.2s, border-color 0.2s',
};

function App() {
  return (
    <BrowserRouter>
      <nav style={navStyle}>
        <div style={{ display: 'flex', alignItems: 'center', marginRight: 32 }}>
          <span style={{ fontSize: 18, fontWeight: 700, color: '#58a6ff' }}>
            Transport Dispatch
          </span>
        </div>
        {[
          { to: '/', label: 'Сеть' },
          { to: '/orders', label: 'Заявки' },
          { to: '/vehicles', label: 'Парк' },
          { to: '/analytics', label: 'Аналитика' },
          { to: '/settings', label: 'Настройки' },
        ].map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            style={({ isActive }) => ({
              ...linkBase,
              color: isActive ? '#58a6ff' : '#8b949e',
              borderBottomColor: isActive ? '#58a6ff' : 'transparent',
            })}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <main style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
        <Routes>
          <Route path="/" element={<Network />} />
          <Route path="/orders" element={<Orders />} />
          <Route path="/vehicles" element={<Vehicles />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);
