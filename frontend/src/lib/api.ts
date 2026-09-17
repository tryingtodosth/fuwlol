/** The one fetch wrapper. Token from localStorage, JSON or FormData bodies, DRF errors
 * surfaced as ApiError with the parsed body so forms can show field messages. */
import { env } from '$env/dynamic/public';

export const API_BASE = (env.PUBLIC_API_BASE_URL || '/api').replace(/\/$/, '');
const TOKEN_KEY = 'fuwlol.token';

export function getToken(): string | null {
	try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string | null) {
	try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ }
}

export class ApiError extends Error {
	constructor(public status: number, public body: unknown) {
		super(describe(body, status));
	}
}

function describe(body: unknown, status: number): string {
	if (body && typeof body === 'object') {
		const b = body as Record<string, unknown>;
		if (typeof b.detail === 'string') return b.detail;
		const parts: string[] = [];
		for (const [k, v] of Object.entries(b)) {
			const msgs = Array.isArray(v) ? v.join(' ') : String(v);
			parts.push(k === 'non_field_errors' ? msgs : `${k}: ${msgs}`);
		}
		if (parts.length) return parts.join('\n');
	}
	if (status === 401) return 'Musisz się zalogować.';
	if (status === 403) return 'Brak uprawnień.';
	if (status === 404) return 'Nie znaleziono.';
	if (status === 429) return 'Za dużo żądań — odczekaj chwilę.';
	return `Błąd serwera (${status}).`;
}

async function request<T>(method: string, path: string, data?: unknown): Promise<T> {
	const headers: Record<string, string> = {};
	const token = getToken();
	if (token) headers.Authorization = `Token ${token}`;
	let body: BodyInit | undefined;
	if (data instanceof FormData) body = data;
	else if (data !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(data); }
	const res = await fetch(`${API_BASE}${path}`, { method, headers, body });
	if (res.status === 204) return undefined as T;
	const text = await res.text();
	let parsed: unknown = null;
	try { parsed = text ? JSON.parse(text) : null; } catch { parsed = text; }
	if (!res.ok) throw new ApiError(res.status, parsed);
	return parsed as T;
}

/** A file behind an authenticated view (escalation evidence): fetched with the token and
 * handed back as a Blob — the browser cannot put an Authorization header on a plain link. */
export async function downloadBlob(path: string): Promise<Blob> {
	const headers: Record<string, string> = {};
	const token = getToken();
	if (token) headers.Authorization = `Token ${token}`;
	const res = await fetch(`${API_BASE}${path}`, { headers });
	if (!res.ok) throw new ApiError(res.status, null);
	return res.blob();
}

export const api = {
	get: <T>(path: string) => request<T>('GET', path),
	post: <T>(path: string, data?: unknown) => request<T>('POST', path, data),
	patch: <T>(path: string, data?: unknown) => request<T>('PATCH', path, data),
	delete: <T>(path: string) => request<T>('DELETE', path)
};

export function qs(params: Record<string, string | number | undefined | null>): string {
	const u = new URLSearchParams();
	for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') u.set(k, String(v));
	const s = u.toString();
	return s ? `?${s}` : '';
}
