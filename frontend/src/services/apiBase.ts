/**
 * The public API origin is deliberately a build-time setting.  Local Vite and
 * the Docker/nginx stack leave it unset and retain same-origin `/api` calls;
 * a separately hosted staging frontend sets VITE_API_BASE_URL to its HTTPS
 * API origin (for example https://databridge-api-staging.onrender.com).
 */
const configuredOrigin = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/$/, '')

export const API_ORIGIN = configuredOrigin || ''
export const API_BASE = `${API_ORIGIN}/api/v1`
export const HEALTH_URL = `${API_ORIGIN}/health`
