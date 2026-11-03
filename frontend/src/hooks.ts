import type { Reroute } from '@sveltejs/kit';

/** ai.fuw.lol is the Koło AI app, served by the same build: on that host every path is the
 * matching route under /ai (`/` → /ai, `/glosowania/3` → /ai/glosowania/3). The URL in the
 * address bar stays as typed. On fuw.lol itself nginx answers /ai… with a 308 to this host,
 * so the /ai routes are only ever reached directly in development. */
export const reroute: Reroute = ({ url }) => {
	if (url.hostname.startsWith('ai.') && !url.pathname.startsWith('/ai')) {
		return url.pathname === '/' ? '/ai' : `/ai${url.pathname}`;
	}
};
