import { useEffect, useMemo, useState } from 'react';
import { Trophy, Users, Loader2, MapPin, Sprout } from 'lucide-react';
import { api } from '../api';

function CommunityCard({ community, highlight = false }) {
  const pct = Math.max(0, Math.min(100, Number(community.progress_percent || 0)));
  return (
    <div
      className="glass-panel"
      style={{
        padding: '1rem',
        border: highlight ? '1px solid rgba(34,197,94,0.35)' : '1px solid var(--glass-border)',
        background: highlight
          ? 'linear-gradient(135deg, rgba(34,197,94,0.14), rgba(8,18,9,0.9))'
          : undefined,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
          <MapPin size={14} color="var(--accent-green)" />
          <strong style={{ fontSize: '0.95rem' }}>{community.ward_name || community.community_id}</strong>
        </div>
        <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{pct}%</span>
      </div>

      <div style={{ height: 8, borderRadius: 999, background: 'rgba(255,255,255,0.08)', overflow: 'hidden', marginBottom: '0.7rem' }}>
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            borderRadius: 999,
            background: 'linear-gradient(90deg, #22c55e, #84cc16)',
          }}
        />
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
        <span>{community.current_value} / {community.target_value} trees</span>
        <span>{community.members_count} members</span>
      </div>
    </div>
  );
}

export default function Community() {
  const [leaderboard, setLeaderboard] = useState([]);
  const [communities, setCommunities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const run = async () => {
      try {
        const [leaderboardData, communitiesData] = await Promise.all([
          api.getCommunityLeaderboard(10),
          api.getCommunities(100),
        ]);
        setLeaderboard(Array.isArray(leaderboardData) ? leaderboardData : []);
        setCommunities(Array.isArray(communitiesData) ? communitiesData : []);
      } catch (e) {
        setError(e.message || 'Could not load community data.');
      } finally {
        setLoading(false);
      }
    };
    run();
  }, []);

  const topCommunity = useMemo(() => {
    if (communities.length === 0) return null;
    const sorted = [...communities].sort(
      (a, b) => (b.progress_percent || 0) - (a.progress_percent || 0)
    );
    return sorted[0];
  }, [communities]);

  return (
    <div style={{ maxWidth: '980px', margin: '0 auto', display: 'grid', gap: '1.2rem' }}>
      <div className="glass-panel" style={{ padding: '1.35rem', border: '1px solid rgba(34,197,94,0.3)' }}>
        <h2 className="text-gradient" style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
          <Users size={24} color="var(--accent-green)" />
          Community Corridors
        </h2>
        <p style={{ margin: '0.55rem 0 0', color: 'var(--text-secondary)' }}>
          Ward leaderboard and live planting progress toward each community target.
        </p>
      </div>

      {loading && (
        <div className="glass-panel" style={{ padding: '1.4rem', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} />
          Loading community progress...
        </div>
      )}

      {!loading && error && (
        <div className="glass-panel" style={{ padding: '1.2rem', border: '1px solid rgba(239,68,68,0.35)', color: '#fca5a5' }}>
          {error}
        </div>
      )}

      {!loading && !error && (
        <>
          {topCommunity && (
            <div className="glass-panel" style={{ padding: '1.2rem', border: '1px solid rgba(34,197,94,0.25)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.8rem' }}>
                <Sprout size={18} color="var(--accent-green)" />
                <strong>Live Progress</strong>
              </div>
              <CommunityCard community={topCommunity} highlight />
            </div>
          )}

          <div className="glass-panel" style={{ padding: '1.1rem' }}>
            <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
              <Trophy size={18} color="#f59e0b" />
              Ward Leaderboard
            </h3>
            <div style={{ display: 'grid', gap: '0.7rem' }}>
              {leaderboard.map((row) => (
                <div
                  key={row.community_id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.7rem 0.9rem',
                    borderRadius: 10,
                    background: 'rgba(255,255,255,0.03)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                    <strong style={{ color: row.rank <= 3 ? '#f59e0b' : 'var(--text-secondary)' }}>#{row.rank}</strong>
                    <span>{row.ward_name || row.community_id}</span>
                  </div>
                  <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    {row.current_value}/{row.target_value} trees ({row.progress_percent}%)
                  </span>
                </div>
              ))}
              {leaderboard.length === 0 && (
                <div style={{ color: 'var(--text-secondary)', fontSize: '0.88rem' }}>
                  No community documents yet. Add records under Firestore `communities` to start tracking.
                </div>
              )}
            </div>
          </div>
        </>
      )}

      <style>{`@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
