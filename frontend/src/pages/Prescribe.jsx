import React, { useState, useEffect } from 'react';
import { MapPin, Loader2, TreePine, Droplets, Wind, CheckCircle, Leaf, Thermometer, FlaskConical, Boxes, Sprout, ChartColumn, TestTube2 } from 'lucide-react';
import { api } from '../api';
import { useNavigate } from 'react-router-dom';

// ── JS-side Bengaluru ward soil lookup (mirrors the backend table) ──
// This runs instantly in the browser as soon as GPS is detected,
// so the user sees the soil type with zero API latency.
const WARD_SOIL_TABLE = [
  {
    zone: 'south', texture: 'Sandy Clay Loam', pH: 6.8,
    organic_carbon_pct: 0.52, nitrogen_kg_ha: 215, soil_health_index: 62,
    lat: [12.88, 12.95], lng: [77.60, 77.66],
  },
  {
    zone: 'east', texture: 'Red Laterite', pH: 7.1,
    organic_carbon_pct: 0.38, nitrogen_kg_ha: 185, soil_health_index: 55,
    lat: [12.93, 13.00], lng: [77.70, 77.78],
  },
  {
    zone: 'north', texture: 'Loamy', pH: 6.5,
    organic_carbon_pct: 0.61, nitrogen_kg_ha: 240, soil_health_index: 70,
    lat: [13.00, 13.12], lng: [77.55, 77.62],
  },
  {
    zone: 'central', texture: 'Clay', pH: 7.3,
    organic_carbon_pct: 0.41, nitrogen_kg_ha: 178, soil_health_index: 52,
    lat: [12.97, 13.02], lng: [77.60, 77.64],
  },
  {
    zone: 'southeast', texture: 'Black Cotton', pH: 6.3,
    organic_carbon_pct: 0.70, nitrogen_kg_ha: 268, soil_health_index: 74,
    lat: [12.82, 12.90], lng: [77.65, 77.72],
  },
];

function detectSoilLocally(lat, lng) {
  // Bounding-box match
  for (const z of WARD_SOIL_TABLE) {
    if (lat >= z.lat[0] && lat <= z.lat[1] && lng >= z.lng[0] && lng <= z.lng[1]) {
      return z;
    }
  }
  // Nearest centroid fallback
  let best = WARD_SOIL_TABLE[0];
  let bestDist = Infinity;
  for (const z of WARD_SOIL_TABLE) {
    const cLat = (z.lat[0] + z.lat[1]) / 2;
    const cLng = (z.lng[0] + z.lng[1]) / 2;
    const d = Math.sqrt((lat - cLat) ** 2 + (lng - cLng) ** 2);
    if (d < bestDist) { bestDist = d; best = z; }
  }
  return best;
}

export default function Prescribe() {
  const [locationStatus, setLocationStatus] = useState('detecting');
  const [loadingAI, setLoadingAI] = useState(false);
  const [coords, setCoords] = useState({ latitude: null, longitude: null });
  const [wardName, setWardName] = useState('');
  const [plotArea, setPlotArea] = useState('10');
  const [localSoil, setLocalSoil] = useState(null);   // instant client-side soil
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!('geolocation' in navigator)) {
      setLocationStatus('error');
      setError('Geolocation is not supported by your browser.');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const lat = position.coords.latitude;
        const lng = position.coords.longitude;
        setCoords({ latitude: lat, longitude: lng });

        // ── Instant soil detection (no API call) ──
        const soil = detectSoilLocally(lat, lng);
        setLocalSoil(soil);

        // ── Reverse geocode ward name ──
        try {
          const res = await fetch(
            `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json`
          );
          const geo = await res.json();
          const ward =
            geo.address?.suburb ||
            geo.address?.neighbourhood ||
            geo.address?.county ||
            geo.address?.city_district || '';
          setWardName(ward);
        } catch { /* ignore */ }

        setLocationStatus('ready');
      },
      () => {
        setLocationStatus('error');
        setError('Location access denied. Please allow GPS and reload.');
      },
      { enableHighAccuracy: true, timeout: 12000 }
    );
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!coords.latitude) return;
    setLoadingAI(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.prescribe({
        coordinates: coords,
        ward_name: wardName,
        plot_area_sqm: parseFloat(plotArea),
      });
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingAI(false);
    }
  };

  const navigate = useNavigate();
  const displaySoil = result?.soil_analysis?.soil || localSoil;

  return (
    <div style={{ maxWidth: '820px', margin: '0 auto' }}>
      <h2 className="text-gradient" style={{ fontSize: '2.5rem', textAlign: 'center', marginBottom: '0.5rem' }}>
        AI Tree Prescription
      </h2>
      <p style={{ color: 'var(--text-secondary)', textAlign: 'center', marginBottom: '2rem' }}>
        Your GPS and soil type are detected automatically.
      </p>

      {/* Location banner */}
      <div className="glass-panel" style={{
        display: 'flex', alignItems: 'center', gap: '1rem',
        padding: '1rem 1.5rem', marginBottom: '1.5rem',
        border: `1px solid ${locationStatus === 'ready' ? 'var(--accent-green)' : locationStatus === 'error' ? '#ef4444' : 'var(--glass-border)'}`,
      }}>
        {locationStatus === 'detecting' && (
          <><Loader2 size={20} color="var(--accent-green)" style={{ animation: 'spin 1s linear infinite', flexShrink: 0 }} />
          <span>Detecting your location…</span></>
        )}
        {locationStatus === 'ready' && (
          <><CheckCircle size={20} color="var(--accent-green)" style={{ flexShrink: 0 }} />
          <div>
            <strong style={{ color: 'var(--accent-green)' }}>Location Detected</strong>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              {coords.latitude?.toFixed(5)}, {coords.longitude?.toFixed(5)}
              {wardName && ` · ${wardName}`}
            </div>
          </div></>
        )}
        {locationStatus === 'error' && (
          <><MapPin size={20} color="#ef4444" style={{ flexShrink: 0 }} />
          <span style={{ color: '#ef4444' }}>{error}</span></>
        )}
      </div>

      {/* Instant soil preview (shows as soon as GPS detects) */}
      {localSoil && locationStatus === 'ready' && (
        <div className="glass-panel" style={{
          marginBottom: '1.5rem', padding: '1rem 1.5rem',
          border: '1px solid rgba(34,197,94,0.25)',
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.75rem'
        }}>
          {[
            { label: 'Soil Type', value: localSoil.texture, Icon: Sprout },
            { label: 'pH', value: localSoil.pH, Icon: FlaskConical },
            { label: 'Organic Carbon', value: `${localSoil.organic_carbon_pct}%`, Icon: Leaf },
            { label: 'Nitrogen', value: `${localSoil.nitrogen_kg_ha} kg/ha`, Icon: TestTube2 },
            { label: 'Health Index', value: `${localSoil.soil_health_index}/100`, Icon: ChartColumn },
            { label: 'Zone', value: `${localSoil.zone} Bengaluru`, Icon: MapPin },
          ].map(({ label, value, Icon }) => (
            <div key={label} style={{ background: 'rgba(0,0,0,0.25)', padding: '0.6rem 0.75rem', borderRadius: '10px' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '0.2rem', display: 'flex', alignItems: 'center', gap: 4 }}>
                <Icon size={11} /> {label}
              </div>
              <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Form */}
      <div className="glass-panel" style={{ marginBottom: '2rem' }}>
        <form onSubmit={handleSubmit}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
            <div>
              <label>Ward / Locality <span style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>(auto-detected)</span></label>
              <input
                type="text"
                placeholder="e.g. Koramangala"
                value={wardName}
                onChange={e => setWardName(e.target.value)}
                required
              />
            </div>
            <div>
              <label>Plot Area (sq meters)</label>
              <input
                type="number"
                min="1"
                value={plotArea}
                onChange={e => setPlotArea(e.target.value)}
                required
              />
            </div>
          </div>

          {error && locationStatus !== 'error' && (
            <div style={{ color: '#ef4444', marginBottom: '1rem', padding: '0.75rem', background: 'rgba(239,68,68,0.1)', borderRadius: '8px' }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            className="btn-primary"
            disabled={loadingAI || locationStatus !== 'ready'}
          >
            {loadingAI
              ? <><Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} /> Getting Gemini Recommendation…</>
              : locationStatus !== 'ready'
              ? <><Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} /> Waiting for GPS…</>
              : 'Get My Tree Prescription'}
          </button>
        </form>
      </div>

      {/* Result */}
      {result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', animation: 'fadeIn 0.5s ease-out' }}>
          {/* Primary recommendation */}
          <div className="glass-panel" style={{ border: '1px solid var(--accent-green)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
              <div style={{ background: 'var(--accent-glow)', padding: '1rem', borderRadius: '50%', flexShrink: 0 }}>
                <TreePine size={32} color="var(--accent-green)" />
              </div>
              <div>
                <h3 style={{ fontSize: '1.75rem', margin: 0 }}>{result.primary_recommendation?.common_name}</h3>
                <p style={{ color: 'var(--text-secondary)', margin: 0, fontStyle: 'italic' }}>
                  {result.primary_recommendation?.scientific_name}
                  {result.primary_recommendation?.kannada_name && ` · ${result.primary_recommendation.kannada_name}`}
                </p>
              </div>
            </div>

            {/* Detected soil used for this recommendation */}
            {displaySoil && (
              <div style={{
                background: 'rgba(34,197,94,0.07)', border: '1px solid rgba(34,197,94,0.2)',
                borderRadius: '10px', padding: '0.75rem 1rem', marginBottom: '1.25rem',
                fontSize: '0.875rem', color: 'var(--text-secondary)'
              }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                  <Sprout size={13} color="var(--accent-green)" /> Recommended for <strong style={{ color: 'var(--text-primary)' }}>{displaySoil.texture}</strong> soil ·
                </span>
                pH {displaySoil.pH} · Nitrogen {displaySoil.nitrogen_kg_ha} kg/ha · Health Score {displaySoil.soil_health_index}/100
              </div>
            )}

            <p style={{ fontSize: '1.05rem', lineHeight: 1.7, marginBottom: '1.5rem' }}>
              {result.primary_recommendation?.why_recommended}
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '1rem' }}>
              {[
                { icon: <Droplets size={20} color="var(--accent-green)" />, label: 'Water Need', value: result.primary_recommendation?.water_requirement },
                { icon: <Wind size={20} color="var(--accent-green)" />, label: 'CO₂ Absorbed', value: `${result.primary_recommendation?.co2_absorption_kg_per_year} kg/yr` },
                { icon: <Leaf size={20} color="var(--accent-green)" />, label: 'Growth Rate', value: result.primary_recommendation?.growth_rate },
                { icon: <Thermometer size={20} color="var(--accent-green)" />, label: 'Canopy Spread', value: `${result.primary_recommendation?.expected_canopy_spread_m}m` },
              ].map(({ icon, label, value }) => (
                <div key={label} style={{ background: 'rgba(0,0,0,0.3)', padding: '1rem', borderRadius: '12px' }}>
                  {icon}
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.4rem' }}>{label}</div>
                  <div style={{ fontWeight: 600 }}>{value}</div>
                </div>
              ))}
            </div>

            {/* View in AR button */}
            <button
              onClick={() => navigate(`/ar?species=${encodeURIComponent(result.primary_recommendation?.common_name || '')}`)}
              style={{
                width: '100%', marginTop: '1rem', padding: '0.85rem',
                background: 'linear-gradient(135deg, rgba(34,197,94,0.12), rgba(16,185,129,0.08))',
                border: '1px solid var(--accent-green)', borderRadius: '12px',
                color: 'var(--accent-green)', cursor: 'pointer', fontWeight: 700,
                fontSize: '0.95rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
              }}
            >
              <Boxes size={18} /> View {result.primary_recommendation?.common_name} in 3D / AR
            </button>
          </div>

          {/* Alternatives */}
          {result.alternative_recommendations?.length > 0 && (
            <div>
              <h4 style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>Also Consider</h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem' }}>
                {result.alternative_recommendations.map((alt, i) => (
                  <div key={i} className="glass-panel" style={{ padding: '1.25rem' }}>
                    <h4 style={{ margin: '0 0 0.25rem 0' }}>{alt.common_name}</h4>
                    <p style={{ fontSize: '0.8rem', fontStyle: 'italic', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>{alt.scientific_name}</p>
                    <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>{alt.why_recommended}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
      `}</style>
    </div>
  );
}
