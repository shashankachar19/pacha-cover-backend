import { useGoogleLogin } from '@react-oauth/google';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Leaf, Shield, TreePine, Satellite } from 'lucide-react';
import LiquidEther from '../components/LiquidEther';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleGoogleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      try {
        // Fetch user profile from Google
        const res = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
          headers: { Authorization: `Bearer ${tokenResponse.access_token}` },
        });
        const profile = await res.json();
        login(profile, tokenResponse.access_token);
        navigate('/');
      } catch (err) {
        console.error('Failed to fetch user profile:', err);
      }
    },
    onError: (err) => console.error('Google login failed:', err),
  });

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'stretch',
      background: 'var(--bg-primary)', position: 'relative', overflow: 'hidden',
    }}>
      <div style={{ position: 'absolute', inset: 0, zIndex: 0, opacity: 0.42, pointerEvents: 'none' }}>
        <LiquidEther
          colors={['#0f2a1a', '#1e6b3a', '#34d399']}
          mouseForce={16}
          cursorSize={86}
          isViscous={true}
          viscous={24}
          iterationsViscous={24}
          iterationsPoisson={20}
          resolution={0.45}
          isBounce={false}
          autoDemo={true}
          autoSpeed={0.38}
          autoIntensity={1.6}
          takeoverDuration={0.25}
          autoResumeDelay={2400}
          autoRampDuration={0.7}
        />
      </div>
      {/* Left panel — branding */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center',
        padding: '4rem', background: 'linear-gradient(135deg, #061206 0%, #0a200a 50%, #061206 100%)',
        position: 'relative', overflow: 'hidden', zIndex: 1,
      }}>
        {/* Background glow orbs */}
        <div style={{ position: 'absolute', width: 400, height: 400, borderRadius: '50%', background: 'radial-gradient(circle, rgba(34,197,94,0.08) 0%, transparent 70%)', top: '10%', left: '-10%', pointerEvents: 'none' }} />
        <div style={{ position: 'absolute', width: 300, height: 300, borderRadius: '50%', background: 'radial-gradient(circle, rgba(34,197,94,0.05) 0%, transparent 70%)', bottom: '15%', right: '-5%', pointerEvents: 'none' }} />

        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '3rem' }}>
          <div style={{ background: 'var(--accent-glow)', padding: '0.75rem', borderRadius: '14px' }}>
            <Leaf size={28} color="var(--accent-green)" />
          </div>
          <span style={{ fontSize: '1.6rem', fontWeight: 800 }}>
            Pacha <span style={{ color: 'var(--accent-green)' }}>Cover</span>
          </span>
        </div>

        <h1 style={{ fontSize: 'clamp(2rem, 4vw, 3rem)', fontWeight: 800, lineHeight: 1.15, marginBottom: '1.5rem' }}>
          Restore Bengaluru's<br />
          <span className="text-gradient">Urban Forest</span>
        </h1>

        <p style={{ fontSize: '1.1rem', color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: '3rem', maxWidth: '400px' }}>
          AI-powered tree prescriptions, satellite heat mapping, and a Green Ledger that rewards every sapling you plant.
        </p>

        {/* Feature list */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {[
            { icon: <Satellite size={18} />, text: 'Google Earth Engine · Live ward heat data' },
            { icon: <TreePine size={18} />, text: 'Gemini AI · Hyper-local tree prescriptions' },
            { icon: <Shield size={18} />, text: 'Green Ledger · Verified sapling points' },
          ].map(({ icon, text }) => (
            <div key={text} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              <span style={{ color: 'var(--accent-green)' }}>{icon}</span>
              {text}
            </div>
          ))}
        </div>
      </div>

      {/* Right panel — login form */}
      <div style={{
        width: '460px', flexShrink: 0, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', padding: '3rem 2.5rem',
        background: 'rgba(8, 15, 8, 0.9)', backdropFilter: 'blur(2px)', borderLeft: '1px solid var(--glass-border)', zIndex: 1,
      }}>
        <div style={{ width: '100%', maxWidth: '340px' }}>
          {/* Header */}
          <div style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
            <div style={{
              width: 64, height: 64, borderRadius: '50%', margin: '0 auto 1.25rem',
              background: 'var(--accent-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              border: '2px solid rgba(34,197,94,0.3)',
            }}>
              <Leaf size={28} color="var(--accent-green)" />
            </div>
            <h2 style={{ fontSize: '1.6rem', fontWeight: 700, marginBottom: '0.4rem' }}>Welcome back</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              Sign in with your Google account to continue
            </p>
          </div>

          {/* Google Sign-In button */}
          <button
            onClick={() => handleGoogleLogin()}
            style={{
              width: '100%', padding: '0.9rem 1.5rem',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.75rem',
              background: '#fff', color: '#1f1f1f', border: 'none',
              borderRadius: '12px', cursor: 'pointer', fontWeight: 600, fontSize: '0.95rem',
              transition: 'all 0.2s', boxShadow: '0 2px 12px rgba(0,0,0,0.3)',
              fontFamily: 'inherit',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = '#f1f3f4'; e.currentTarget.style.boxShadow = '0 4px 20px rgba(0,0,0,0.4)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = '#fff'; e.currentTarget.style.boxShadow = '0 2px 12px rgba(0,0,0,0.3)'; }}
          >
            {/* Google logo SVG */}
            <svg width="20" height="20" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            Continue with Google
          </button>

          {/* Divider */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', margin: '1.75rem 0' }}>
            <div style={{ flex: 1, height: '1px', background: 'var(--glass-border)' }} />
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>SECURED BY</span>
            <div style={{ flex: 1, height: '1px', background: 'var(--glass-border)' }} />
          </div>

          {/* Trust badges */}
          <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem' }}>
            {['Google OAuth 2.0', 'Firebase Auth', 'HTTPS'].map(badge => (
              <span key={badge} style={{
                fontSize: '0.65rem', padding: '0.25rem 0.6rem', borderRadius: '999px',
                background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)',
                color: 'var(--text-secondary)',
              }}>
                {badge}
              </span>
            ))}
          </div>

          <p style={{ textAlign: 'center', fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '2rem', lineHeight: 1.6 }}>
            By signing in, you agree to contribute to Bengaluru's urban reforestation. Your green actions are tracked on the public ledger.
          </p>
        </div>
      </div>
    </div>
  );
}
