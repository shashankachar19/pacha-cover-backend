import { useRef, useState } from 'react';
import { Camera, CheckCircle2, AlertCircle, Loader2, Leaf, Award, Upload, BookOpen, MapPin, Navigation } from 'lucide-react';
import { api } from '../api';

function haversineKm(lat1, lon1, lat2, lon2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const R = 6371;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function isInsideGeofence(lat, lon, geofence) {
  const center = geofence?.center;
  const radiusKm = Number(geofence?.radius_km);
  if (!center || Number.isNaN(radiusKm) || radiusKm <= 0) return false;
  const dist = haversineKm(lat, lon, Number(center.latitude), Number(center.longitude));
  return dist <= radiusKm;
}

async function deriveWardFromLiveData(lat, lon) {
  const communities = await api.getCommunities(200);
  if (!Array.isArray(communities) || communities.length === 0) {
    return null;
  }

  const ranked = communities
    .map((c) => {
      const center = c?.geofence?.center;
      if (!center) return null;
      return {
        wardName: c.ward_name || c.community_id,
        dist: haversineKm(lat, lon, Number(center.latitude), Number(center.longitude)),
        inside: isInsideGeofence(lat, lon, c.geofence),
      };
    })
    .filter(Boolean)
    .sort((a, b) => {
      if (a.inside !== b.inside) return a.inside ? -1 : 1;
      return a.dist - b.dist;
    });

  return ranked[0]?.wardName || null;
}

export default function Verify() {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [savedToLedger, setSavedToLedger] = useState(false);
  const [ledgerError, setLedgerError] = useState(null);
  const [spotId, setSpotId] = useState(null);
  const [speciesInput, setSpeciesInput] = useState('');
  const [wardInput, setWardInput] = useState('');
  const [coords, setCoords] = useState({ latitude: null, longitude: null, capturedAt: null });
  const [locating, setLocating] = useState(false);

  const captureCurrentLocation = async ({ silent = false } = {}) => {
    if (!navigator.geolocation) {
      if (!silent) setError('Geolocation is not supported in this browser.');
      return null;
    }

    setLocating(true);
    if (!silent) setError(null);

    const position = await new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(
        resolve,
        reject,
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
      );
    }).catch(() => null);

    if (!position) {
      setLocating(false);
      if (!silent) setError('Could not capture live location. Please allow location access and retry.');
      return null;
    }

    const latitude = Number(position.coords.latitude.toFixed(6));
    const longitude = Number(position.coords.longitude.toFixed(6));
    const capturedAt = new Date().toISOString();

    setCoords({ latitude, longitude, capturedAt });

    try {
      const wardName = await deriveWardFromLiveData(latitude, longitude);
      if (wardName) {
        setWardInput(wardName);
      }

      setLocating(false);
      return { latitude, longitude, capturedAt, wardName };
    } catch {
      setLocating(false);
      if (!silent) setError('Unable to infer ward from live community data. Please retry.');
      return { latitude, longitude, capturedAt, wardName: null };
    }
  };

  const handleFileChange = (e) => {
    const f = e.target.files[0];
    if (!f) return;
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setResult(null);
    setError(null);
    setSavedToLedger(false);
    setLedgerError(null);
    setSpotId(null);
  };

  const handleVerify = async () => {
    if (!file) return;

    setLoading(true);
    setError(null);
    setResult(null);
    setSavedToLedger(false);
    setLedgerError(null);
    setSpotId(null);

    let createdSpotId = null;

    try {
      let liveLocation = {
        latitude: coords.latitude,
        longitude: coords.longitude,
        wardName: wardInput,
      };

      liveLocation = await captureCurrentLocation();
      if (!liveLocation) {
        throw new Error('Live location is required to create a new spot.');
      }

      if (!liveLocation.wardName) {
        throw new Error('Unable to infer ward from live community data. Please retry.');
      }

      const spot = await api.adoptSpot({
        coordinates: {
          latitude: liveLocation.latitude,
          longitude: liveLocation.longitude,
        },
        spot_name: `${speciesInput || 'Sapling'} - live verification`,
        ward_name: liveLocation.wardName,
        species_common_name: speciesInput || 'Unknown species',
        species_scientific_name: null,
        notes: `Submitted ${new Date().toLocaleDateString('en-IN')} using live GPS capture`,
        is_public: true,
      });

      createdSpotId = spot?.spot_id || null;
      if (!createdSpotId) {
        throw new Error('Spot was not created correctly. Please try again.');
      }

      setSavedToLedger(true);

      setSpotId(createdSpotId);

      const data = await api.verifyGrowth({
        spotId: createdSpotId,
        imageFile: file,
      });
      setResult(data);
    } catch (err) {
      setError(err.message);
      if (createdSpotId) {
        setLedgerError('Spot is saved in your ledger, but verification failed. You can retry verification for this spot.');
      }
    } finally {
      setLoading(false);
    }
  };

  const clearImage = () => {
    setFile(null);
    setPreview(null);
    setResult(null);
    setError(null);
    setSavedToLedger(false);
    setLedgerError(null);
    setSpotId(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  const approved = result?.status === 'approved';

  return (
    <div style={{ maxWidth: '700px', margin: '0 auto' }}>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />

      <h2 className="text-gradient" style={{ fontSize: '2.5rem', textAlign: 'center', marginBottom: '0.5rem' }}>
        Green Ledger Verification
      </h2>
      <p style={{ color: 'var(--text-secondary)', textAlign: 'center', marginBottom: '2rem' }}>
        Live GPS location is captured automatically before creating and verifying your spot.
      </p>

      <div className="glass-panel" style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
          <div>
            <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.35rem' }}>
              Tree Species
            </label>
            <input type="text" placeholder="e.g. Neem, Peepal..." value={speciesInput} onChange={(e) => setSpeciesInput(e.target.value)} />
          </div>
          <div>
            <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.35rem' }}>
              Ward / Area (auto)
            </label>
            <input type="text" value={wardInput || 'Detecting from live community data...'} readOnly />
          </div>
        </div>

        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: '0.75rem',
            padding: '0.75rem 0.85rem',
            marginBottom: '1.25rem',
            borderRadius: '10px',
            border: '1px solid var(--glass-border)',
            background: 'rgba(255,255,255,0.02)',
            flexWrap: 'wrap',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
            <Navigation size={14} color="var(--accent-green)" />
            {coords.latitude != null && coords.longitude != null
              ? `Live location: ${coords.latitude}, ${coords.longitude}`
              : 'Live location not captured yet'}
          </div>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => captureCurrentLocation()}
            disabled={locating}
            style={{ whiteSpace: 'nowrap' }}
          >
            <MapPin size={15} />
            {locating ? 'Capturing...' : 'Refresh Live Location'}
          </button>
        </div>

        {preview ? (
          <div style={{ position: 'relative', textAlign: 'center', marginBottom: '1.5rem' }}>
            <img src={preview} alt="preview" style={{ maxWidth: '100%', maxHeight: '300px', borderRadius: '12px', objectFit: 'cover' }} />
            <button
              onClick={clearImage}
              style={{
                position: 'absolute',
                top: 10,
                right: 10,
                background: 'rgba(0,0,0,0.75)',
                color: '#fff',
                border: 'none',
                borderRadius: '50%',
                width: 30,
                height: 30,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              x
            </button>
          </div>
        ) : (
          <div
            onClick={() => inputRef.current?.click()}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: '220px',
              border: '2px dashed var(--accent-green)',
              borderRadius: '16px',
              cursor: 'pointer',
              background: 'rgba(34,197,94,0.04)',
              marginBottom: '1.5rem',
            }}
          >
            <Camera size={52} color="var(--accent-green)" style={{ marginBottom: '0.75rem' }} />
            <span style={{ fontSize: '1.1rem', fontWeight: 600 }}>Click to Upload Image</span>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.4rem' }}>JPEG, PNG, WebP, max 10MB</span>
          </div>
        )}

        {preview && (
          <button onClick={() => inputRef.current?.click()} className="btn-secondary" style={{ width: '100%', marginBottom: '1rem' }}>
            <Upload size={16} /> Change Image
          </button>
        )}

        {error && (
          <div style={{ color: '#ef4444', marginBottom: '1rem', padding: '0.75rem', background: 'rgba(239,68,68,0.1)', borderRadius: '8px' }}>
            {error}
          </div>
        )}

        <button className="btn-primary" onClick={handleVerify} disabled={!file || loading || locating}>
          {loading ? (
            <>
              <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} /> Verifying with live data...
            </>
          ) : (
            <>
              <Leaf size={18} /> Verify Sapling
            </>
          )}
        </button>
      </div>

      {result && (
        <div className="glass-panel" style={{ border: `1px solid ${approved ? 'var(--accent-green)' : '#ef4444'}`, animation: 'fadeIn 0.5s ease-out' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.25rem' }}>
            {approved ? <CheckCircle2 size={36} color="var(--accent-green)" /> : <AlertCircle size={36} color="#ef4444" />}
            <div>
              <h3 style={{ margin: 0, color: approved ? 'var(--accent-green)' : '#ef4444' }}>
                {approved ? 'Sapling Verified!' : 'Verification Failed'}
              </h3>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                Confidence: {Math.round((result.confidence_score || 0) * 100)}%
              </div>
            </div>
          </div>

          <p style={{ lineHeight: 1.7, color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
            {result.message || (approved ? 'Image verified as a valid sapling.' : 'Could not confirm as a planted sapling.')}
          </p>
          {approved && (
            <div
              style={{
                marginBottom: '1rem',
                padding: '0.75rem 0.9rem',
                borderRadius: '10px',
                background: 'rgba(34,197,94,0.08)',
                border: '1px solid rgba(34,197,94,0.25)',
                fontSize: '0.82rem',
                color: 'var(--accent-green)',
              }}
            >
              {result.community_update_status === 'updated' && `Community updated in ${result.community_matched_count} geofence(s).`}
              {result.community_update_status === 'no_match' && 'Verification passed, but no configured community geofence matched this spot.'}
              {result.community_update_status === 'failed' && 'Verification passed, but community aggregation update failed. Please retry shortly.'}
              {result.community_update_status === 'skipped_not_approved' && 'Community update skipped because verification was not approved.'}
            </div>
          )}

          {result.detected_labels?.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1.5rem' }}>
              {result.detected_labels.map((label, index) => (
                <span
                  key={index}
                  style={{
                    padding: '0.25rem 0.75rem',
                    borderRadius: '999px',
                    background: 'rgba(34,197,94,0.1)',
                    border: '1px solid rgba(34,197,94,0.3)',
                    fontSize: '0.8rem',
                    color: 'var(--accent-green)',
                  }}
                >
                  {label}
                </span>
              ))}
            </div>
          )}

          {approved && (
            <div style={{ padding: '1.25rem', background: 'var(--accent-glow)', borderRadius: '12px', textAlign: 'center' }}>
              <Award size={28} color="var(--accent-green)" style={{ marginBottom: '0.5rem' }} />
              <div style={{ fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '1px', fontWeight: 600 }}>Green Points Awarded</div>
              <div style={{ fontSize: '3rem', fontWeight: 800, lineHeight: 1.1 }}>+{result.green_points_awarded}</div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Added to your Green Ledger</div>
            </div>
          )}

          {savedToLedger && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '1rem', padding: '0.75rem 1rem', background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.25)', borderRadius: '10px' }}>
              <BookOpen size={16} color="var(--accent-green)" />
              <span style={{ fontSize: '0.85rem', color: 'var(--accent-green)' }}>
                Saved to Firestore ledger{spotId ? ` (Spot ID: ${spotId})` : ''}
              </span>
            </div>
          )}

          {ledgerError && (
            <div style={{ marginTop: '0.75rem', fontSize: '0.8rem', color: '#f59e0b', padding: '0.5rem 0.75rem', background: 'rgba(245,158,11,0.08)', borderRadius: '8px' }}>
              {ledgerError}
            </div>
          )}
        </div>
      )}

      <style>{`@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}@keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}`}</style>
    </div>
  );
}
