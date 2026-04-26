import React, { useState, useRef, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Info, Satellite, Activity, Thermometer, TreePine, Droplets, TrendingUp, Leaf } from 'lucide-react';

// AI-generated photorealistic tree images (local assets — always load)
const TREE_PHOTOS = {
  neem:              '/trees/neem.png',
  peepal:            '/trees/peepal.png',
  mango:             '/trees/mango.png',
  'rain tree':       '/trees/raintree.png',
  'indian rosewood': '/trees/default.png',
  jackfruit:         '/trees/default.png',
  gulmohar:          '/trees/default.png',
  tamarind:          '/trees/default.png',
  banyan:            '/trees/peepal.png',
  arjuna:            '/trees/default.png',
};

const SPECIES_INFO = {
  neem:            { scientific: 'Azadirachta indica',    kannada: 'ಬೇವು',     co2: 20, canopy: 10, water: 'Low',    growth: 'Fast' },
  peepal:          { scientific: 'Ficus religiosa',       kannada: 'ಅರಳಿ',    co2: 22, canopy: 15, water: 'Low',    growth: 'Moderate' },
  mango:           { scientific: 'Mangifera indica',      kannada: 'ಮಾವು',    co2: 18, canopy: 10, water: 'Medium', growth: 'Moderate' },
  'rain tree':     { scientific: 'Samanea saman',         kannada: 'ಮಳೆ ಮರ',  co2: 35, canopy: 25, water: 'Low',    growth: 'Fast' },
  'indian rosewood': { scientific: 'Dalbergia latifolia', kannada: 'ಬೀಟಿ',    co2: 28, canopy: 12, water: 'Low',    growth: 'Slow' },
  jackfruit:       { scientific: 'Artocarpus heterophyllus', kannada: 'ಹಲಸು', co2: 25, canopy: 12, water: 'Medium', growth: 'Moderate' },
  gulmohar:        { scientific: 'Delonix regia',         kannada: 'ಗುಲ್ಮೊಹರ್', co2: 15, canopy: 12, water: 'Low', growth: 'Fast' },
  banyan:          { scientific: 'Ficus benghalensis',    kannada: 'ಆಲ',      co2: 40, canopy: 30, water: 'Low',    growth: 'Slow' },
  arjuna:          { scientific: 'Terminalia arjuna',     kannada: 'ಅರ್ಜುನ',  co2: 22, canopy: 10, water: 'Low',    growth: 'Moderate' },
};

const DEFAULT_INFO = { scientific: 'Native Species', kannada: '', co2: 20, canopy: 10, water: 'Low', growth: 'Moderate' };
const DEFAULT_PHOTO = '/trees/default.png';

function getBySpecies(name, map, fallback) {
  if (!name) return fallback;
  const lower = name.toLowerCase();
  for (const [k, v] of Object.entries(map)) {
    if (lower.includes(k)) return v;
  }
  return fallback;
}

export default function AR() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const species = params.get('species') || '';
  const info = getBySpecies(species, SPECIES_INFO, DEFAULT_INFO);
  const photoUrl = getBySpecies(species, TREE_PHOTOS, DEFAULT_PHOTO);

  const cardRef = useRef(null);
  const [tilt, setTilt] = useState({ x: 0, y: 0 });
  const [scanning, setScanning] = useState(true);
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setScanning(false), 2200);
    return () => clearTimeout(t);
  }, []);

  const handleMouseMove = (e) => {
    const rect = cardRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = ((e.clientY - rect.top) / rect.height - 0.5) * -18;
    const y = ((e.clientX - rect.left) / rect.width - 0.5) * 18;
    setTilt({ x, y });
  };

  return (
    <div style={{ maxWidth: '960px', margin: '0 auto' }}>
      <button onClick={() => navigate(-1)} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
        <ArrowLeft size={16} /> Back
      </button>

      <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
        <h2 className="text-gradient" style={{ fontSize: '2.2rem', marginBottom: '0.25rem' }}>
          {species || 'Native Tree'} · AR View
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontStyle: 'italic' }}>{info.scientific}{info.kannada && ` · ${info.kannada}`}</p>
      </div>

      {/* 3D tilt card */}
      <div
        ref={cardRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setTilt({ x: 0, y: 0 })}
        style={{
          perspective: '1200px', marginBottom: '1.5rem',
          borderRadius: '20px', cursor: 'grab',
        }}
      >
        <div style={{
          transform: `rotateX(${tilt.x}deg) rotateY(${tilt.y}deg) scale(1.02)`,
          transition: tilt.x === 0 ? 'transform 0.6s ease' : 'transform 0.1s',
          borderRadius: '20px', overflow: 'hidden',
          height: '480px', position: 'relative',
          boxShadow: `0 30px 80px rgba(34,197,94,0.15), 0 0 0 1px rgba(34,197,94,0.2)`,
        }}>
          {/* Real tree photo */}
          <img
            src={imgError ? DEFAULT_PHOTO : photoUrl}
            alt={species}
            onError={() => setImgError(true)}
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
          />

          {/* Dark gradient overlay */}
          <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(5,15,5,0.85) 0%, rgba(5,15,5,0.1) 50%, transparent 100%)' }} />

          {/* AR scanning overlay */}
          {scanning && (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{
                width: '200px', height: '200px', border: '2px solid var(--accent-green)',
                borderRadius: '4px', position: 'relative', animation: 'scanPulse 0.4s ease-in-out infinite alternate',
              }}>
                {[['0 0', 'top left'], ['auto 0', 'top right'], ['0 auto', 'bottom left'], ['auto auto', 'bottom right']].map(([pos, key]) => (
                  <div key={key} style={{
                    position: 'absolute', width: 20, height: 20,
                    borderColor: 'var(--accent-green)', borderStyle: 'solid', borderWidth: 0,
                    ...(key.includes('top') ? { top: -2, borderTopWidth: 3 } : { bottom: -2, borderBottomWidth: 3 }),
                    ...(key.includes('left') ? { left: -2, borderLeftWidth: 3 } : { right: -2, borderRightWidth: 3 }),
                  }} />
                ))}
              </div>
            </div>
          )}

          {/* AR HUD overlays */}
          {!scanning && <>
            {/* Top-left tag */}
            <div style={{ position: 'absolute', top: 16, left: 16, background: 'rgba(0,0,0,0.6)', border: '1px solid rgba(34,197,94,0.5)', borderRadius: '8px', padding: '6px 12px', backdropFilter: 'blur(8px)' }}>
              <div style={{ fontSize: '0.65rem', color: 'var(--accent-green)', letterSpacing: '2px' }}>PACHA COVER AR</div>
              <div style={{ fontSize: '0.75rem', color: '#fff', fontWeight: 600 }}>{species || 'Native Species'}</div>
            </div>

            {/* Top-right coords */}
            <div style={{ position: 'absolute', top: 16, right: 16, background: 'rgba(0,0,0,0.5)', borderRadius: '8px', padding: '6px 10px', fontSize: '0.65rem', color: 'rgba(255,255,255,0.6)', backdropFilter: 'blur(8px)', textAlign: 'right' }}>
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><Satellite size={11} /> GEE VERIFIED</div>
              <div style={{ color: 'var(--accent-green)', display: 'inline-flex', alignItems: 'center', gap: 4 }}><Activity size={11} /> LIVE DATA</div>
            </div>

            {/* Data points */}
            {[
              { x: '20%', y: '40%', label: `CO₂ −${info.co2}kg/yr`, delay: '0s', Icon: Thermometer },
              { x: '72%', y: '30%', label: `Canopy ${info.canopy}m`, delay: '0.2s', Icon: TreePine },
              { x: '60%', y: '65%', label: `Water: ${info.water}`, delay: '0.4s', Icon: Droplets },
            ].map(({ x, y, label, delay, Icon }) => (
              <div key={label} style={{
                position: 'absolute', left: x, top: y,
                animation: `fadeIn 0.5s ease ${delay} both`,
              }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent-green)', boxShadow: '0 0 8px var(--accent-green)', margin: 'auto' }} />
                <div style={{ marginTop: 4, background: 'rgba(0,0,0,0.7)', border: '1px solid rgba(34,197,94,0.4)', borderRadius: 6, padding: '3px 8px', fontSize: '0.72rem', color: '#fff', whiteSpace: 'nowrap', backdropFilter: 'blur(6px)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                  <Icon size={11} /> {label}
                </div>
              </div>
            ))}

            {/* Bottom species info */}
            <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, padding: '1.5rem', background: 'linear-gradient(to top, rgba(0,0,0,0.9), transparent)' }}>
              <h3 style={{ margin: 0, fontSize: '1.5rem' }}>{species}</h3>
              <p style={{ margin: '0.25rem 0 0', color: 'rgba(255,255,255,0.6)', fontSize: '0.85rem', fontStyle: 'italic' }}>{info.scientific}</p>
            </div>
          </>}
        </div>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: '0.75rem', marginBottom: '1.5rem' }}>
        {[
          { label: 'CO₂/year', value: `${info.co2} kg`, Icon: Leaf },
          { label: 'Canopy', value: `${info.canopy}m`, Icon: TreePine },
          { label: 'Water', value: info.water, Icon: Droplets },
          { label: 'Growth', value: info.growth, Icon: TrendingUp },
        ].map(({ label, value, Icon }) => (
          <div key={label} className="glass-panel" style={{ padding: '0.85rem', textAlign: 'center' }}>
            <div style={{ marginBottom: '0.25rem' }}><Icon size={14} color="var(--accent-green)" /></div>
            <div style={{ fontWeight: 700, fontSize: '1.05rem', color: 'var(--accent-green)' }}>{value}</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>{label}</div>
          </div>
        ))}
      </div>

      <div className="glass-panel" style={{ padding: '1rem 1.25rem', border: '1px solid rgba(34,197,94,0.2)', display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
        <Info size={16} color="var(--accent-green)" style={{ flexShrink: 0, marginTop: 2 }} />
        <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          This is a <strong style={{ color: 'var(--text-primary)' }}>photorealistic AI-recommended view</strong> of <em>{species}</em> trees found in Bengaluru.
          Tilt your mouse for a 3D parallax effect. On a mobile device, tap <strong style={{ color: 'var(--accent-green)' }}>Launch AR</strong> to place a 3D tree in your real environment.
        </p>
      </div>

      <style>{`
        @keyframes fadeIn { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:none; } }
        @keyframes scanPulse { from { opacity:1; } to { opacity:0.3; } }
      `}</style>
    </div>
  );
}
