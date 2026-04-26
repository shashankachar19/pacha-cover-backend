import React, { useState, useEffect } from 'react';
import { MapContainer, TileLayer, CircleMarker, Tooltip } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { Thermometer, Leaf, Loader2, AlertTriangle, Flame, Satellite, Zap, BarChart3, MapPin, X } from 'lucide-react';
import { BENGALURU_WARDS, getWardRisk } from '../data/bengaluruWards';
import { api } from '../api';

const RISK_CFG = {
  low:      { color: '#22c55e', label: 'Low Risk', Icon: Leaf },
  moderate: { color: '#f59e0b', label: 'Moderate', Icon: Thermometer },
  high:     { color: '#f97316', label: 'High Risk', Icon: Flame },
  critical: { color: '#ef4444', label: 'Critical', Icon: AlertTriangle },
};

// Deterministic fallback (instant, always works)
const FALLBACK_WARDS = BENGALURU_WARDS.map(w => ({ ...w, ...getWardRisk(w) }));

// Map API ward to display format
function apiWardToDisplay(apiW) {
  const level = apiW.heat_risk_level || apiW.heat_risk_score > 75 ? 'critical'
    : apiW.heat_risk_score > 55 ? 'high'
    : apiW.heat_risk_score > 35 ? 'moderate' : 'low';
  return {
    id: apiW.ward_id,
    name: apiW.ward_name,
    lat: BENGALURU_WARDS.find(w => w.id === apiW.ward_id)?.lat || 12.9716,
    lng: BENGALURU_WARDS.find(w => w.id === apiW.ward_id)?.lng || 77.5946,
    lst: apiW.avg_land_surface_temp,
    ndvi: apiW.avg_ndvi,
    score: apiW.heat_risk_score,
    level: typeof apiW.heat_risk_level === 'string' ? apiW.heat_risk_level : level,
    adopted: apiW.adopted_spots_count || 0,
    isReal: true,
  };
}


export default function Heatmap() {
  const [wardsData, setWardsData]   = useState(FALLBACK_WARDS);
  const [filter, setFilter]         = useState('all');
  const [search, setSearch]         = useState('');
  const [showAll, setShowAll]       = useState(false);
  const [selectedWard, setSelected] = useState(null);
  const [apiStatus, setApiStatus]   = useState('loading'); // 'loading' | 'real' | 'fallback'

  useEffect(() => {
    let cancelled = false;
    const timeout = setTimeout(() => {
      if (!cancelled && apiStatus === 'loading') setApiStatus('fallback');
    }, 12000); // 12s timeout before giving up

    api.getHeatmap()
      .then(resp => {
        if (cancelled) return;
        const apiWards = (resp.wards || []).map(apiWardToDisplay);
        if (apiWards.length > 0) {
          // Merge: use real data where available, keep fallback for the rest
          const realMap = Object.fromEntries(apiWards.map(w => [w.id, w]));
          setWardsData(FALLBACK_WARDS.map(fw => realMap[fw.id] || fw));
          setApiStatus('real');
        } else {
          setApiStatus('fallback');
        }
      })
      .catch(() => { if (!cancelled) setApiStatus('fallback'); })
      .finally(() => clearTimeout(timeout));

    return () => { cancelled = true; clearTimeout(timeout); };
  }, []);

  const ALL_WARDS_DATA = wardsData;

  const filtered = ALL_WARDS_DATA.filter(w => {
    const matchFilter = filter === 'all' || w.level === filter;
    const matchSearch = w.name.toLowerCase().includes(search.toLowerCase());
    return matchFilter && matchSearch;
  });

  const displayed = showAll ? filtered : filtered.slice(0, 12);

  const stats = {
    critical: ALL_WARDS_DATA.filter(w => w.level === 'critical').length,
    high:     ALL_WARDS_DATA.filter(w => w.level === 'high').length,
    moderate: ALL_WARDS_DATA.filter(w => w.level === 'moderate').length,
    low:      ALL_WARDS_DATA.filter(w => w.level === 'low').length,
    avgLst:   (ALL_WARDS_DATA.reduce((s, w) => s + w.lst, 0) / ALL_WARDS_DATA.length).toFixed(1),
  };
  const selectedCfg = selectedWard ? RISK_CFG[selectedWard.level] : null;

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
        <h2 className="text-gradient" style={{ fontSize: '2.5rem', marginBottom: '0.4rem' }}>
          Bengaluru Heat Map
        </h2>
        <p style={{ color: 'var(--text-secondary)' }}>
          All 198 BBMP wards · Urban Heat Island analysis · Google Earth Engine
        </p>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem', padding: '0.3rem 0.9rem', borderRadius: '999px', fontSize: '0.75rem', fontWeight: 600,
          background: apiStatus === 'real' ? 'rgba(34,197,94,0.12)' : apiStatus === 'loading' ? 'rgba(255,255,255,0.05)' : 'rgba(245,158,11,0.1)',
          border: `1px solid ${apiStatus === 'real' ? 'rgba(34,197,94,0.3)' : apiStatus === 'loading' ? 'rgba(255,255,255,0.1)' : 'rgba(245,158,11,0.3)'}`,
          color: apiStatus === 'real' ? 'var(--accent-green)' : apiStatus === 'loading' ? 'var(--text-secondary)' : '#f59e0b',
        }}>
          {apiStatus === 'loading' && <><Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> Loading GEE data…</>}
          {apiStatus === 'real'    && <><Satellite size={12} /> Live GEE Data — Google Earth Engine</>}
          {apiStatus === 'fallback'&& <><Zap size={12} /> Fast Mode — Deterministic model (GEE unavailable)</>}
        </div>
      </div>

      {/* Summary stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.75rem', marginBottom: '1.5rem' }}>
        {[
          { label: 'Avg Temperature', value: `${stats.avgLst}°C`, color: '#f97316', Icon: Thermometer },
          { label: 'Critical', value: stats.critical, color: '#ef4444', Icon: AlertTriangle },
          { label: 'High Risk', value: stats.high, color: '#f97316', Icon: Flame },
          { label: 'Moderate', value: stats.moderate, color: '#f59e0b', Icon: Thermometer },
          { label: 'Low Risk', value: stats.low, color: '#22c55e', Icon: Leaf },
          { label: 'Total Wards', value: 198, color: 'var(--accent-green)', Icon: BarChart3 },
        ].map(({ label, value, color, Icon }) => (
          <div key={label} className="glass-panel" style={{ padding: '0.85rem', textAlign: 'center' }}>
            <div style={{ marginBottom: '0.2rem' }}><Icon size={14} color={color} /></div>
            <div style={{ fontSize: '1.4rem', fontWeight: 800, color }}>{value}</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>{label}</div>
          </div>
        ))}
      </div>

      {/* MAP */}
      <div style={{ borderRadius: '16px', overflow: 'hidden', border: '1px solid var(--glass-border)', marginBottom: '1.5rem', height: '460px' }}>
        <MapContainer
          center={[12.9716, 77.5946]}
          zoom={11}
          style={{ height: '100%', width: '100%', background: '#0a1a0a' }}
          zoomControl={true}
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; <a href="https://carto.com">CARTO</a>'
          />
          {ALL_WARDS_DATA.map(ward => {
            const cfg = RISK_CFG[ward.level];
            return (
              <CircleMarker
                key={ward.id}
                center={[ward.lat, ward.lng]}
                radius={filter === 'all' ? 7 : (filter === ward.level ? 10 : 5)}
                pathOptions={{
                  color: cfg.color,
                  fillColor: cfg.color,
                  fillOpacity: filter === 'all' || filter === ward.level ? 0.75 : 0.2,
                  weight: selectedWard?.id === ward.id ? 3 : 1,
                }}
                eventHandlers={{ click: () => setSelected(ward) }}
              >
                <Tooltip direction="top" offset={[0, -4]} opacity={0.95}>
                  <div style={{ fontSize: '12px', padding: '2px 4px' }}>
                    <strong>{ward.name}</strong><br />
                    <cfg.Icon size={12} style={{ marginRight: 4 }} /> {cfg.label} · {ward.score}/100<br />
                    <Thermometer size={12} style={{ marginRight: 4 }} /> {ward.lst}°C · <Leaf size={12} style={{ marginRight: 4 }} /> NDVI {ward.ndvi}
                  </div>
                </Tooltip>
              </CircleMarker>
            );
          })}
        </MapContainer>
      </div>

      {/* Selected ward detail */}
      {selectedWard && (
        <div className="glass-panel" style={{
          marginBottom: '1.5rem', padding: '1.25rem',
          border: `1px solid ${selectedCfg.color}55`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem'
        }}>
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{selectedWard.id}</div>
            <h3 style={{ margin: '0.25rem 0' }}>{selectedWard.name}</h3>
            <span style={{ padding: '0.2rem 0.6rem', borderRadius: '999px', fontSize: '0.75rem', fontWeight: 600, background: selectedCfg.color + '22', color: selectedCfg.color }}>
              <selectedCfg.Icon size={12} style={{ marginRight: 4 }} /> {selectedCfg.label}
            </span>
          </div>
          <div style={{ display: 'flex', gap: '1.5rem' }}>
            {[
              { label: 'LST', value: `${selectedWard.lst}°C`, Icon: Thermometer },
              { label: 'NDVI', value: selectedWard.ndvi, Icon: Leaf },
              { label: 'Heat Score', value: `${selectedWard.score}/100`, Icon: BarChart3 },
              { label: 'Coords', value: `${selectedWard.lat.toFixed(4)}, ${selectedWard.lng.toFixed(4)}`, Icon: MapPin },
            ].map(({ label, value, Icon }) => (
              <div key={label} style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                  <Icon size={11} /> {label}
                </div>
                <div style={{ fontWeight: 700 }}>{value}</div>
              </div>
            ))}
          </div>
          <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: '1.2rem' }}><X size={18} /></button>
        </div>
      )}

      {/* Legend */}
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.25rem', flexWrap: 'wrap', alignItems: 'center' }}>
        {Object.entries(RISK_CFG).map(([key, cfg]) => (
          <button key={key} onClick={() => setFilter(filter === key ? 'all' : key)} style={{
            display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.4rem 1rem',
            borderRadius: '999px', border: `1px solid ${cfg.color}55`, cursor: 'pointer',
            background: filter === key ? cfg.color + '33' : 'transparent',
            color: filter === key ? cfg.color : 'var(--text-secondary)', fontSize: '0.85rem', fontWeight: 600,
          }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: cfg.color, display: 'inline-block' }} />
            <cfg.Icon size={13} /> {cfg.label}
          </button>
        ))}
        <button onClick={() => setFilter('all')} style={{
          marginLeft: 'auto', padding: '0.4rem 1rem', borderRadius: '999px',
          border: '1px solid var(--glass-border)', background: filter === 'all' ? 'var(--accent-green)' : 'transparent',
          color: filter === 'all' ? '#000' : 'var(--text-secondary)', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600,
        }}>Show All</button>
      </div>

      {/* Search */}
      <div style={{ marginBottom: '1.25rem' }}>
        <input
          type="text"
          placeholder="Search ward name…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ maxWidth: '320px' }}
        />
      </div>

      {/* Ward cards grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '1rem' }}>
        {displayed.map(ward => {
          const cfg = RISK_CFG[ward.level];
          return (
            <div
              key={ward.id}
              className="glass-panel"
              onClick={() => setSelected(ward)}
              style={{ padding: '1rem', border: `1px solid ${cfg.color}33`, cursor: 'pointer', transition: 'transform 0.15s' }}
              onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'}
              onMouseLeave={e => e.currentTarget.style.transform = 'none'}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>{ward.name}</div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>{ward.id}</div>
                </div>
                <span style={{ fontSize: '0.75rem', padding: '0.15rem 0.5rem', borderRadius: '999px', background: cfg.color + '22', color: cfg.color, fontWeight: 600 }}>
                  <cfg.Icon size={12} />
                </span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.5rem', fontSize: '0.8rem' }}>
                <div><div style={{ color: 'var(--text-secondary)', fontSize: '0.65rem' }}>LST</div><strong style={{ color: cfg.color }}>{ward.lst}°C</strong></div>
                <div><div style={{ color: 'var(--text-secondary)', fontSize: '0.65rem' }}>NDVI</div><strong>{ward.ndvi}</strong></div>
                <div><div style={{ color: 'var(--text-secondary)', fontSize: '0.65rem' }}>Score</div><strong>{ward.score}/100</strong></div>
              </div>
              {/* Heat score bar */}
              <div style={{ marginTop: '0.75rem', height: '4px', background: 'rgba(255,255,255,0.08)', borderRadius: '2px' }}>
                <div style={{ height: '100%', width: `${ward.score}%`, background: cfg.color, borderRadius: '2px', transition: 'width 0.6s' }} />
              </div>
            </div>
          );
        })}
      </div>

      {/* See All / Show Less */}
      {filtered.length > 12 && (
        <div style={{ textAlign: 'center', marginTop: '1.5rem' }}>
          <button
            onClick={() => setShowAll(!showAll)}
            className="btn-primary"
            style={{ width: 'auto', padding: '0.75rem 2.5rem' }}
          >
            {showAll ? 'Show Less' : `See All ${filtered.length} Wards`}
          </button>
        </div>
      )}

      <style>{`
        .leaflet-container { font-family: inherit; }
        .leaflet-tooltip { background: #0d1f12; border: 1px solid #22c55e55; color: #e2e8f0; border-radius: 8px; }
        .leaflet-tooltip::before { display: none; }
      `}</style>
    </div>
  );
}
