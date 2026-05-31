const BACKEND_BASE_URL = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_BACKEND_URL) || 'http://localhost:8000';

export { BACKEND_BASE_URL };
