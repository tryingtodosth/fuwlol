import { api, getToken, setToken, ApiError } from './api';
import type { User } from './types';

let user = $state<User | null>(null);
let ready = $state(false);

export const auth = {
	get user() { return user; },
	get ready() { return ready; },
	get isAuthenticated() { return user !== null; },
	get isStaff() { return !!user?.is_staff; },
	async init() {
		if (getToken()) {
			try { user = await api.get<User>('/auth/me/'); }
			catch (e) { if (e instanceof ApiError && e.status === 401) setToken(null); }
		}
		ready = true;
	},
	async login(username: string, password: string) {
		const r = await api.post<{ token: string; user: User }>('/auth/login/', { username, password });
		setToken(r.token); user = r.user;
	},
	async register(username: string, email: string, password: string) {
		const r = await api.post<{ token: string; user: User }>('/auth/register/', { username, email, password });
		setToken(r.token); user = r.user;
	},
	async logout() {
		try { await api.post('/auth/logout/'); } catch { /* token already gone */ }
		setToken(null); user = null;
	}
};
