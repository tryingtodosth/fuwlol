/** How many rows a moderation queue answered with — whatever envelope it used. The portrait and
 * consent queues are different apps and one of them paginates; the pages that only want to say
 * „Portrety (3)” next to a link should not have to know which shape they got, or break the day
 * the other one starts paginating too. */
export function queueSize(r: unknown): number {
	if (Array.isArray(r)) return r.length;
	if (r && typeof r === 'object') {
		const o = r as { count?: unknown; items?: unknown; results?: unknown };
		if (typeof o.count === 'number') return o.count;
		if (Array.isArray(o.items)) return o.items.length;
		if (Array.isArray(o.results)) return o.results.length;
	}
	return 0;
}
