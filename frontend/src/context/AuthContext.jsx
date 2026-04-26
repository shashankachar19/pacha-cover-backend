import { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const saved = localStorage.getItem('pacha_user');
      return saved ? JSON.parse(saved) : null;
    } catch { return null; }
  });

  const [token, setToken] = useState(() => localStorage.getItem('pacha_token') || null);

  const login = (googleUser, credential) => {
    setUser(googleUser);
    setToken(credential);
    localStorage.setItem('pacha_user', JSON.stringify(googleUser));
    localStorage.setItem('pacha_token', credential);
  };

  const logout = () => {
    setUser(null);
    setToken(null);
    localStorage.removeItem('pacha_user');
    localStorage.removeItem('pacha_token');
  };

  return (
    <AuthContext.Provider value={{ user, token, login, logout, isLoggedIn: !!user }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
