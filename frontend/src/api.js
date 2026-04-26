// Centralized API Client — uses Google OAuth token from AuthContext

const API_BASE = '/api/v1';

function getToken() {
  return localStorage.getItem('pacha_token') || null;
}

async function fetchWithAuth(endpoint, options = {}) {
  const token = getToken();
  const defaultHeaders = {
    'Accept': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
  };
  if (!(options.body instanceof FormData)) {
    defaultHeaders['Content-Type'] = 'application/json';
  }
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: { ...defaultHeaders, ...options.headers },
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `API Error: ${response.status}`);
  }
  return response.json();
}

export const api = {
  // ── Prescription ──────────────────────────────────────────────────────────
  prescribe: async (data) =>
    fetchWithAuth('/prescribe', { method: 'POST', body: JSON.stringify(data) }),

  // ── Verification ──────────────────────────────────────────────────────────
  verifyImage: async (imageFile) => {
    const formData = new FormData();
    formData.append('image', imageFile);
    return fetchWithAuth('/verify-image', { method: 'POST', body: formData });
  },

  verifyGrowth: async ({ spotId, imageFile }) => {
    const formData = new FormData();
    formData.append('spot_id', spotId);
    formData.append('image', imageFile);
    return fetchWithAuth('/verify-growth', { method: 'POST', body: formData });
  },

  // ── Green Ledger / Firestore ──────────────────────────────────────────────
  adoptSpot: async (data) =>
    fetchWithAuth('/ledger/adopt', { method: 'POST', body: JSON.stringify(data) }),

  getMySpots: async () =>
    fetchWithAuth('/ledger/my-spots', { method: 'GET' }),

  getCommunitySpots: async (wardName) =>
    fetchWithAuth(`/ledger/community${wardName ? `?ward_name=${wardName}` : ''}`, { method: 'GET' }),

  getLeaderboard: async (limit = 5) =>
    fetchWithAuth(`/ledger/leaderboard?limit=${limit}`, { method: 'GET' }),

  getWardCorridors: async (wardId) =>
    fetchWithAuth(`/corridors/ward/${wardId}`, { method: 'GET' }),

  getCommunities: async (limit = 50) =>
    fetchWithAuth(`/communities?limit=${limit}`, { method: 'GET' }),

  getCommunityLeaderboard: async (limit = 10) =>
    fetchWithAuth(`/communities/leaderboard?limit=${limit}`, { method: 'GET' }),

  // ── Heatmap ───────────────────────────────────────────────────────────────
  getHeatmap: async () => fetchWithAuth('/heatmap', { method: 'GET' }),
};
