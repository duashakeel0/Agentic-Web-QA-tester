// VITE_API_BASE_URL is baked in at build time (Vercel/Netlify env var
// setting) - falls back to localhost:8000 unchanged for local dev, so
// this file never needs a manual edit for either environment.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
