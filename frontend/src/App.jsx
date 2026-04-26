import { BrowserRouter as Router, Routes, Route, NavLink, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { GoogleOAuthProvider } from '@react-oauth/google';
import { Leaf, LogOut, ChevronDown, House, Map, Sparkles, Cuboid, BadgeCheck, Users, UserCircle2 } from 'lucide-react';
import { useState } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import Home from './pages/Home';
import Prescribe from './pages/Prescribe';
import Verify from './pages/Verify';
import Heatmap from './pages/Heatmap';
import AR from './pages/AR';
import Login from './pages/Login';
import Profile from './pages/Profile';
import Community from './pages/Community';
import NatureMotion from './components/NatureMotion';
import Dock from './components/Dock';
import './index.css';

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

// ── Protected route wrapper ────────────────────────────────────────────────────
function Protected({ children }) {
  const { isLoggedIn } = useAuth();
  return isLoggedIn ? children : <Navigate to="/login" replace />;
}

// ── User avatar dropdown ───────────────────────────────────────────────────────
function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          display: 'flex', alignItems: 'center', gap: '0.5rem',
          background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.25)',
          borderRadius: '999px', padding: '0.35rem 0.75rem 0.35rem 0.35rem',
          cursor: 'pointer', color: 'var(--text-primary)',
        }}
      >
        {user?.picture
          ? <img src={user.picture} alt={user.name} style={{ width: 28, height: 28, borderRadius: '50%', objectFit: 'cover' }} />
          : <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'var(--accent-green)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 700, color: '#000' }}>{user?.name?.[0]}</div>
        }
        <span style={{ fontSize: '0.85rem', maxWidth: '100px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user?.given_name || user?.name}</span>
        <ChevronDown size={14} color="var(--text-secondary)" />
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 8px)', right: 0,
          background: '#0d1f0d', border: '1px solid var(--glass-border)',
          borderRadius: '12px', minWidth: '200px', zIndex: 100, overflow: 'hidden',
          boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
        }}>
          <div style={{ padding: '0.75rem 1rem', borderBottom: '1px solid var(--glass-border)' }}>
            <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>{user?.name}</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{user?.email}</div>
          </div>
          <button
            onClick={() => { setOpen(false); navigate('/profile'); }}
            style={{ width: '100%', padding: '0.75rem 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-primary)', fontSize: '0.85rem', textAlign: 'left' }}
          >
            <UserCircle2 size={15} /> View Profile
          </button>
          <button
            onClick={handleLogout}
            style={{
              width: '100%', padding: '0.75rem 1rem', display: 'flex', alignItems: 'center',
              gap: '0.5rem', background: 'none', border: 'none', cursor: 'pointer',
              color: '#ef4444', fontSize: '0.85rem', textAlign: 'left',
            }}
          >
            <LogOut size={15} /> Sign Out
          </button>
        </div>
      )}
    </div>
  );
}

// ── Navbar ─────────────────────────────────────────────────────────────────────
function Navbar() {
  const { isLoggedIn } = useAuth();

  return (
    <nav className="navbar">
      <NavLink to="/" className="nav-brand">
        <Leaf size={24} color="var(--accent-green)" />
        Pacha<span>Cover</span>
      </NavLink>
      {isLoggedIn && (
        <div className="nav-links">
          <UserMenu />
        </div>
      )}
    </nav>
  );
}

// ── App ────────────────────────────────────────────────────────────────────────
function AppRoutes() {
  const { isLoggedIn } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const tabs = [
    { to: '/', label: 'Home', icon: <House size={18} /> },
    { to: '/heatmap', label: 'Heatmap', icon: <Map size={18} /> },
    { to: '/prescribe', label: 'Prescribe', icon: <Sparkles size={18} /> },
    { to: '/ar', label: 'AR View', icon: <Cuboid size={18} /> },
    { to: '/verify', label: 'Verify', icon: <BadgeCheck size={18} /> },
    { to: '/community', label: 'Community', icon: <Users size={18} /> },
  ];

  const dockItems = tabs.map((tab) => {
    const isActive = tab.to === '/' ? location.pathname === '/' : location.pathname.startsWith(tab.to);
    return {
      icon: tab.icon,
      label: tab.label,
      onClick: () => navigate(tab.to),
      className: isActive ? 'is-active' : '',
    };
  });

  return (
    <div className="app-container">
      <Navbar />
      <NatureMotion key={location.pathname} />
      <main className={isLoggedIn ? 'main-with-dock' : ''}>
        <div className="page-transition" key={location.pathname}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<Protected><Home /></Protected>} />
            <Route path="/heatmap" element={<Protected><Heatmap /></Protected>} />
            <Route path="/community" element={<Protected><Community /></Protected>} />
            <Route path="/prescribe" element={<Protected><Prescribe /></Protected>} />
            <Route path="/ar" element={<Protected><AR /></Protected>} />
            <Route path="/verify" element={<Protected><Verify /></Protected>} />
            <Route path="/profile" element={<Protected><Profile /></Protected>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </main>
      {isLoggedIn && (
        <div className="bottom-dock-fixed">
          <Dock
            items={dockItems}
            panelHeight={62}
            dockHeight={74}
            baseItemSize={42}
            magnification={48}
            distance={120}
            spring={{ mass: 0.28, stiffness: 110, damping: 30 }}
          />
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
      <AuthProvider>
        <Router>
          <AppRoutes />
        </Router>
      </AuthProvider>
    </GoogleOAuthProvider>
  );
}
