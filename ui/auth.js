/**
 * Auth utility — stores JWT from /auth/login in localStorage.
 * Call initAuth() on page load to restore session.
 * If no valid token, redirects to login.
 */

const API_BASE = 'http://192.168.50.100:9001';
const TOKEN_KEY = 'tms_token';
const USER_KEY = 'tms_user';

// ── Init ─────────────────────────────────────────────────────────────────────

function initAuth() {
  const token = getToken();
  if (!token) {
    redirectToLogin();
    return false;
  }
  if (isTokenExpired(token)) {
    clearAuth();
    redirectToLogin();
    return false;
  }
  return true;
}

// ── Getters / Setters ─────────────────────────────────────────────────────────

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function getUser() {
  const u = localStorage.getItem(USER_KEY);
  return u ? JSON.parse(u) : null;
}

function setAuth(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

// ── Token helpers ─────────────────────────────────────────────────────────────

function isTokenExpired(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    const now = Math.floor(Date.now() / 1000);
    return payload.exp ? payload.exp < now : false;
  } catch {
    return true;
  }
}

// ── Auth header helper (for fetch calls) ──────────────────────────────────────

function authHeaders() {
  const token = getToken();
  return token
    ? { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
    : { 'Content-Type': 'application/json' };
}

// ── Login / Logout ───────────────────────────────────────────────────────────

async function login(email, password) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Login failed' }));
    throw new Error(err.detail || 'Login failed');
  }
  const data = await res.json();
  setAuth(data.access_token, data);
  return data;
}

function logout() {
  clearAuth();
  redirectToLogin();
}

function redirectToLogin() {
  window.location.href = 'login.html';
}

// ── Generic authenticated fetch ───────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...authHeaders(), ...options.headers },
  });
  if (res.status === 401) {
    clearAuth();
    redirectToLogin();
    throw new Error('Session expired');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Role helpers ───────────────────────────────────────────────────────────────

function userRole() {
  return getUser()?.role || null;
}

function isAdmin() {
  return userRole() === 'admin';
}

function canWrite(resource) {
  const role = userRole();
  if (!role) return false;
  // admin and accounting can write invoices
  if (resource === 'invoices') return role === 'admin' || role === 'accounting';
  return role === 'admin';
}

function canDelete() {
  return isAdmin();
}