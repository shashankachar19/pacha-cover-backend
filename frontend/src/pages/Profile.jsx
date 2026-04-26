import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { LogOut, MapPin, Mail, Calendar, Leaf, TreePine, Award, TrendingUp, Users, Star, CheckCircle2, Loader2, Lock, ShieldCheck, Sprout, FlaskConical, Trophy, Medal } from 'lucide-react';
import { api } from '../api';

const SPECIES_TO_PHOTO = {
  neem: '/trees/neem.png', peepal: '/trees/peepal.png',
  mango: '/trees/mango.png', 'rain tree': '/trees/raintree.png',
};
function photoForSpecies(name) {
  const k = (name || '').toLowerCase();
  for (const [key, val] of Object.entries(SPECIES_TO_PHOTO)) if (k.includes(key)) return val;
  return '/trees/default.png';
}
const STAGE_LABEL = (v) => v === 'verified' || v === 'completed' ? 'Established' : v === 'planted' ? 'Growing' : 'Sapling';
const STAGE_COLOR = (v) => v === 'verified' || v === 'completed' ? '#22c55e' : v === 'planted' ? '#f59e0b' : '#3b82f6';
const STAGE_PCT = (v) => v === 'verified' || v === 'completed' ? 90 : v === 'planted' ? 55 : 25;

function SaplingCard({ s }) {
  const pct = STAGE_PCT(s.status);
  const col = STAGE_COLOR(s.status);
  return (
    <div className="glass-panel" style={{ padding: 0, overflow: 'hidden', border: '1px solid var(--glass-border)' }}>
      <div style={{ height: 130, overflow: 'hidden', position: 'relative' }}>
        <img src={photoForSpecies(s.species_common_name)} alt={s.species_common_name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        <div style={{ position: 'absolute', top: 8, right: 8, background: 'rgba(0,0,0,0.7)', borderRadius: '6px', padding: '2px 8px', fontSize: '0.7rem', color: '#22c55e', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
          <CheckCircle2 size={11} /> {s.status}
        </div>
      </div>
      <div style={{ padding: '0.85rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
          <div>
            <div style={{ fontWeight: 700 }}>{s.species_common_name}</div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>{s.ward_name}</div>
          </div>
          <div style={{ textAlign: 'right', fontSize: '0.72rem', color: col, fontWeight: 600 }}>{STAGE_LABEL(s.status)}</div>
        </div>
        <div style={{ marginTop: '0.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.65rem', color: 'var(--text-secondary)', marginBottom: 3 }}><span>Growth</span><span>{pct}%</span></div>
          <div style={{ height: 5, background: 'rgba(255,255,255,0.08)', borderRadius: 3 }}><div style={{ height: '100%', width: `${pct}%`, background: col, borderRadius: 3 }} /></div>
        </div>
        <div style={{ marginTop: '0.5rem', fontSize: '0.68rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4 }}>
          <CheckCircle2 size={11} color="#22c55e" /> {s.green_points_earned} pts · {new Date(s.adopted_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
        </div>
        {s.notes && <div style={{ marginTop: '0.4rem', fontSize: '0.7rem', color: 'var(--text-secondary)', fontStyle: 'italic', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.notes}</div>}
      </div>
    </div>
  );
}

export default function Profile() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [spots, setSpots] = useState([]);
  const [leaderboardRaw, setLeaderboard] = useState([]);
  const [corridors, setCorridors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [spotsData, lbData] = await Promise.all([
          api.getMySpots(),
          api.getLeaderboard(5)
        ]);
        setSpots(Array.isArray(spotsData) ? spotsData : []);
        setLeaderboard(Array.isArray(lbData) ? lbData : []);

        const ward = spotsData[0]?.ward_name;
        if (ward) {
          const wardId = ward.toLowerCase().replace(/ /g, '_');
          const corrData = await api.getWardCorridors(wardId);
          setCorridors(Array.isArray(corrData) ? corrData : []);
        }
      } catch (e) {
        setFetchError(e.message);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const treesPlanted = spots.length;
  const totalPoints = spots.reduce((s, t) => s + (t.green_points_earned || 0), 0);
  const totalCO2 = treesPlanted * 18;
  const taxRebate = Math.min(100, Math.round((totalPoints / 1000) * 100));
  const joined = new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' });
  const primaryWard = spots[0]?.ward_name || 'Bengaluru';

  const rank = totalPoints >= 500 ? { label: 'Forest Guardian', color: '#f59e0b', Icon: Trophy }
             : totalPoints >= 200 ? { label: 'Tree Champion',   color: '#22c55e', Icon: TreePine }
             : totalPoints >= 50  ? { label: 'Green Starter',   color: '#3b82f6', Icon: Sprout }
             :                      { label: 'Seedling',         color: '#94a3b8', Icon: Leaf };
  const nextThreshold = totalPoints >= 500 ? 1000 : totalPoints >= 200 ? 500 : totalPoints >= 50 ? 200 : 50;

  // Merge "You" into leaderboard if not already there
  let leaderboard = [...leaderboardRaw];
  const isYouInTop = leaderboard.some(r => r.uid === user?.sub || r.email === user?.email);
  if (!isYouInTop) {
    leaderboard.push({
      uid: user?.sub || 'me',
      name: 'You',
      total_green_points: totalPoints,
      ward: primaryWard,
      isYou: true
    });
    leaderboard.sort((a, b) => (b.total_green_points || b.pts || 0) - (a.total_green_points || a.pts || 0));
  }
  // Standardise format
  leaderboard = leaderboard.slice(0, 5).map((r, i) => ({
    rank: i + 1,
    name: r.isYou || r.uid === user?.sub ? 'You' : r.name,
    pts: r.total_green_points ?? r.pts,
    ward: r.ward || (r.isYou ? primaryWard : 'Bengaluru'),
    isYou: r.isYou || r.uid === user?.sub
  }));

  const activeCorridor = corridors[0] || { corridor_name: `${primaryWard} Corridor`, tree_count: 0, status: 'Checking...' };

  return (
    <div style={{ maxWidth: '960px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

      {/* ── Identity ── */}
      <div className="glass-panel" style={{ padding: '1.75rem', background: 'linear-gradient(135deg,rgba(34,197,94,0.06) 0%,rgba(5,15,5,0.9) 100%)', border: '1px solid rgba(34,197,94,0.2)' }}>
        <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flexShrink: 0 }}>
            {user?.picture
              ? <img src={user.picture} alt={user.name} style={{ width: 90, height: 90, borderRadius: '50%', border: '3px solid var(--accent-green)', objectFit: 'cover' }} />
              : <div style={{ width: 90, height: 90, borderRadius: '50%', background: 'var(--accent-green)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '2rem', fontWeight: 700, color: '#000' }}>{user?.name?.[0]}</div>
            }
            <div style={{ position: 'absolute', bottom: 3, right: 3, background: '#22c55e', borderRadius: '50%', width: 16, height: 16, border: '2px solid #050f05' }} />
          </div>
          <div style={{ flex: 1, minWidth: 220 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '0.35rem' }}>
              <h2 style={{ margin: 0, fontSize: '1.55rem' }}>{user?.name}</h2>
              <span style={{ padding: '0.18rem 0.65rem', borderRadius: '999px', fontSize: '0.75rem', fontWeight: 700, background: rank.color + '22', color: rank.color, border: `1px solid ${rank.color}44`, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                <rank.Icon size={13} /> {rank.label}
              </span>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.9rem', color: 'var(--text-secondary)', fontSize: '0.82rem', marginBottom: '0.9rem' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}><Mail size={13} />{user?.email}</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}><MapPin size={13} />{primaryWard}, Bengaluru</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}><Calendar size={13} />Joined {joined}</span>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <span style={{ padding: '0.2rem 0.6rem', borderRadius: '6px', fontSize: '0.72rem', background: 'rgba(34,197,94,0.1)', color: 'var(--accent-green)', border: '1px solid rgba(34,197,94,0.25)', display: 'inline-flex', alignItems: 'center', gap: 4 }}><Lock size={11} /> Google OAuth 2.0</span>
              <span style={{ padding: '0.2rem 0.6rem', borderRadius: '6px', fontSize: '0.72rem', background: 'rgba(59,130,246,0.1)', color: '#3b82f6', border: '1px solid rgba(59,130,246,0.25)', display: 'inline-flex', alignItems: 'center', gap: 4 }}><ShieldCheck size={11} /> Verified Citizen</span>
              {corridors.length > 0 && <span style={{ padding: '0.2rem 0.6rem', borderRadius: '6px', fontSize: '0.72rem', background: 'rgba(245,158,11,0.1)', color: '#f59e0b', border: '1px solid rgba(245,158,11,0.25)', display: 'inline-flex', alignItems: 'center', gap: 4 }}><Leaf size={11} /> {activeCorridor.corridor_name}</span>}
            </div>
            <div style={{ marginTop: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginBottom: 4 }}>
                <span style={{ color: 'var(--text-secondary)' }}>Pacha Points</span>
                <span style={{ color: rank.color, fontWeight: 700 }}>{totalPoints} / {nextThreshold}</span>
              </div>
              <div style={{ height: '8px', background: 'rgba(255,255,255,0.08)', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${Math.min(100,(totalPoints/nextThreshold)*100)}%`, background: `linear-gradient(90deg,${rank.color},var(--accent-green))`, borderRadius: '4px' }} />
              </div>
            </div>
          </div>
          <button onClick={() => { logout(); navigate('/login'); }} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.5rem 1rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: '8px', color: '#ef4444', cursor: 'pointer', fontSize: '0.82rem', fontWeight: 600 }}>
            <LogOut size={14} /> Sign Out
          </button>
        </div>
      </div>

      {/* ── Green Ledger Stats ── */}
      <div>
        <h3 style={{ margin: '0 0 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Leaf size={18} color="var(--accent-green)" /> Green Ledger Stats</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: '1rem' }}>
          {[
            { label: 'Trees Planted',   value: treesPlanted, unit: 'Firestore verified', color: '#22c55e', icon: <TreePine size={20} /> },
            { label: 'CO₂ Offset',      value: `${totalCO2}kg`, unit: 'absorbed/year', color: '#34d399', icon: <Leaf size={20} /> },
            { label: 'Pacha Points',    value: totalPoints, unit: 'total earned', color: '#f59e0b', icon: <Award size={20} /> },
            { label: 'Ward Rank',       value: leaderboard.find(l => l.isYou)?.rank || '-', unit: `of ${leaderboard.length} users`, color: '#a78bfa', icon: <TrendingUp size={20} /> },
          ].map(({ label, value, unit, color, icon }) => (
            <div key={label} className="glass-panel" style={{ padding: '1.25rem', textAlign: 'center' }}>
              <div style={{ color, marginBottom: '0.4rem' }}>{icon}</div>
              <div style={{ fontSize: '2rem', fontWeight: 800, color, lineHeight: 1 }}>{value}</div>
              <div style={{ fontWeight: 600, fontSize: '0.82rem', margin: '0.25rem 0 0.15rem' }}>{label}</div>
              <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}>{unit}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Tree Library ── */}
      <div>
        <h3 style={{ margin: '0 0 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <TreePine size={18} color="var(--accent-green)" /> My Tree Library
          <span style={{ marginLeft: 'auto', fontSize: '0.8rem', fontWeight: 400, color: 'var(--text-secondary)' }}>
            {loading ? 'Loading…' : `${treesPlanted} saplings from Firestore`}
          </span>
        </h3>

        {loading && <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: 'var(--text-secondary)', padding: '2rem' }}><Loader2 size={20} style={{ animation: 'spin 1s linear infinite' }} /> Loading…</div>}
        
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(220px,1fr))', gap: '1rem' }}>
          {spots.map(s => <SaplingCard key={s.spot_id} s={s} />)}
          <div onClick={() => navigate('/verify')} className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', border: '2px dashed rgba(34,197,94,0.3)', cursor: 'pointer', textAlign: 'center', minHeight: 240 }}>
            <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>+</div>
            <div style={{ fontWeight: 600, color: 'var(--accent-green)', marginBottom: '0.25rem' }}>Add Sapling</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Verify a new planting</div>
          </div>
        </div>
      </div>

      {/* ── Community & Leaderboard ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem' }}>
        <div className="glass-panel" style={{ padding: '1.25rem', border: '1px solid rgba(34,197,94,0.25)' }}>
          <h4 style={{ margin: '0 0 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Users size={16} color="var(--accent-green)" /> Community Role</h4>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', padding: '0.85rem', background: 'rgba(34,197,94,0.07)', borderRadius: '12px', marginBottom: '0.85rem' }}>
            <div style={{ fontSize: '2rem', color: 'var(--accent-green)' }}><Leaf size={30} /></div>
            <div>
              <div style={{ fontWeight: 700, color: 'var(--accent-green)' }}>{activeCorridor.corridor_name}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                {corridors.length > 0 ? 'Active Corridor Member' : `No active corridors in ${primaryWard} yet`}
              </div>
            </div>
          </div>
          {[
            { label: 'Corridor Trees', value: activeCorridor.tree_count || '-', Icon: Sprout },
            { label: 'Location', value: primaryWard, Icon: MapPin },
            { label: 'Status', value: corridors.length > 0 ? 'Active Cluster' : 'Monitoring', Icon: FlaskConical },
          ].map(({ label, value, Icon }) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', padding: '0.35rem 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
              <span style={{ color: 'var(--text-secondary)', display: 'inline-flex', alignItems: 'center', gap: 4 }}><Icon size={12} /> {label}</span><span style={{ fontWeight: 600 }}>{value}</span>
            </div>
          ))}
        </div>

        <div className="glass-panel" style={{ padding: '1.25rem' }}>
          <h4 style={{ margin: '0 0 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Star size={16} color="#f59e0b" /> Top Planters <span style={{ marginLeft: 'auto', fontSize: '0.72rem', color: 'var(--text-secondary)', fontWeight: 400 }}>City-wide</span></h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {leaderboard.map(({ rank, name, pts, ward, isYou }) => (
              <div key={rank} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.6rem 0.75rem', borderRadius: '10px', background: isYou ? 'rgba(34,197,94,0.1)' : 'rgba(255,255,255,0.03)', border: isYou ? '1px solid rgba(34,197,94,0.3)' : '1px solid transparent' }}>
                <span style={{ width: 22, textAlign: 'center', fontWeight: 700, color: rank <= 3 ? ['#f59e0b','#94a3b8','#b45309'][rank-1] : 'var(--text-secondary)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
                  {rank <= 3 ? <Medal size={14} /> : `#${rank}`}
                </span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: isYou ? 700 : 400, color: isYou ? 'var(--accent-green)' : 'var(--text-primary)', fontSize: '0.85rem' }}>{name}</div>
                  <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}>{ward}</div>
                </div>
                <span style={{ fontWeight: 700, color: isYou ? 'var(--accent-green)' : 'var(--text-secondary)', fontSize: '0.85rem' }}>{pts} pts</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <style>{`@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
