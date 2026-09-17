import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.setOptions({ gfm: true, breaks: true });

/** Markdown → sanitized HTML. Image names that match an attachment become its URL; an
 * image naming nothing we have becomes a plain "(brak pliku: name)" so the reader is told
 * rather than shown a broken picture. Math is typeset afterwards by `typeset()`. */
export interface RenderOptions { images?: boolean }

/** Only pictures that resolve to one of OUR attachment URLs (or an editor preview blob)
 * survive sanitizing. This is the real "no external images" rule: the regex rewrite of
 * `![](url)` below is a courtesy that tells the reader what was dropped, but reference-style
 * images and raw <img> tags never went through it — so the decision is made here, on the
 * DOM, for every path (Markdown, LaTeX.js, chat). A hot-linked picture is a tracking pixel
 * that fires on every moderator who opens the page. */
let allowedImageUrls = new Set<string>();
export function withAllowedImages<T>(urls: Iterable<string>, fn: () => T): T {
	const previous = allowedImageUrls;
	allowedImageUrls = new Set(urls);
	try { return fn(); } finally { allowedImageUrls = previous; }
}
/** A resolver wrapped so that everything it hands out is remembered as allowed. */
export function trackingResolver(resolve: (name: string) => string | undefined, seen: Set<string>) {
	return (name: string) => { const u = resolve(name); if (u) seen.add(u); return u; };
}

let hooked = false;
export function hookSanitizer() {
	if (hooked) return;
	hooked = true;
	DOMPurify.addHook('uponSanitizeAttribute', (node, data) => {
		if (node.tagName === 'IMG' && data.attrName === 'src' && !allowedImageUrls.has(data.attrValue)) {
			data.keepAttr = false;
		}
		if (node.tagName === 'IMG' && (data.attrName === 'srcset' || data.attrName === 'loading')) data.keepAttr = false;
	});
	DOMPurify.addHook('afterSanitizeAttributes', (node) => {
		// every link opens in a new tab and is nofollow — user content, never a vote for the target
		if (node.tagName === 'A' && node.getAttribute('href')) {
			node.setAttribute('target', '_blank');
			node.setAttribute('rel', 'nofollow noopener');
		}
		if (node.tagName === 'IMG' && !node.getAttribute('src')) node.remove(); // an image with no picture is nothing
	});
}
const hookLinks = hookSanitizer;

export function renderMarkdown(src: string, resolve: (name: string) => string | undefined, options: RenderOptions = {}): string {
	hookLinks();
	if (options.images === false) {
		// the chat board: no pictures at all — an image becomes its alt text, or nothing
		src = src.replace(/!\[([^\]]*)\]\([^)]*\)/g, (_m, alt) => (alt ? `(${alt})` : ''));
	}
	const seen = new Set<string>();
	const track = trackingResolver(resolve, seen);
	const withImages = src.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (m, alt, ref) => {
		if (/^(https?:)?\/\//i.test(ref) || ref.startsWith('data:')) return `(zewnętrzny obraz pominięty: ${ref})`;
		const url = track(ref);
		return url ? `![${alt}](${url})` : `(brak pliku: ${ref})`;
	});
	const html = marked.parse(withImages, { async: false }) as string;
	// `class` is deliberately not allowed: user content borrowing the app's own classes
	// (a `pill--amber` "Wyróżnione", a fake moderation notice) is a phishing surface, and
	// nothing legitimate in Markdown needs one — KaTeX adds its own classes after this.
	return withAllowedImages(options.images === false ? [] : seen, () => DOMPurify.sanitize(html, {
		ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'b', 'i', 'u', 's', 'code', 'pre', 'blockquote', 'ul', 'ol', 'li', 'a', 'img',
			'h1', 'h2', 'h3', 'h4', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'span', 'div', 'sup', 'sub'],
		ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'target', 'rel'],
		ALLOWED_URI_REGEXP: /^(?:https?:|mailto:|blob:|\/)/i
	}));
}

let katexReady: Promise<(el: HTMLElement) => void> | null = null;
/** KaTeX auto-render (lazy — only pages with content pay for it). `$…$` and `\(…\)` inline,
 * `$$…$$` and `\[…\]` display. Errors render as red text, never throw. */
export function typeset(el: HTMLElement): Promise<void> {
	katexReady ??= Promise.all([
		import('katex/contrib/auto-render'),
		import('katex/dist/katex.min.css')
	]).then(([m]) => (target: HTMLElement) =>
		m.default(target, {
			delimiters: [
				{ left: '$$', right: '$$', display: true },
				{ left: '\\[', right: '\\]', display: true },
				{ left: '\\(', right: '\\)', display: false },
				{ left: '$', right: '$', display: false }
			],
			throwOnError: false,
			ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code', 'a']
		})
	);
	return katexReady.then((fn) => fn(el));
}
