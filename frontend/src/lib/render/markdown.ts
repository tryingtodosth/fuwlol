import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.setOptions({ gfm: true, breaks: true });

/** Markdown → sanitized HTML. Image names that match an attachment become its URL; an
 * image naming nothing we have becomes a plain "(brak pliku: name)" so the reader is told
 * rather than shown a broken picture. Math is typeset afterwards by `typeset()`. */
export interface RenderOptions { images?: boolean }

let hooked = false;
function hookLinks() {
	if (hooked) return;
	hooked = true;
	// every link opens in a new tab and is nofollow — user content, never a vote for the target
	DOMPurify.addHook('afterSanitizeAttributes', (node) => {
		if (node.tagName === 'A' && node.getAttribute('href')) {
			node.setAttribute('target', '_blank');
			node.setAttribute('rel', 'nofollow noopener');
		}
	});
}

export function renderMarkdown(src: string, resolve: (name: string) => string | undefined, options: RenderOptions = {}): string {
	hookLinks();
	if (options.images === false) {
		// the chat board: no pictures at all — an image becomes its alt text, or nothing
		src = src.replace(/!\[([^\]]*)\]\([^)]*\)/g, (_m, alt) => (alt ? `(${alt})` : ''));
	}
	const withImages = src.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (m, alt, ref) => {
		if (/^(https?:)?\/\//i.test(ref) || ref.startsWith('data:')) return `(zewnętrzny obraz pominięty: ${ref})`;
		const url = resolve(ref);
		return url ? `![${alt}](${url})` : `(brak pliku: ${ref})`;
	});
	const html = marked.parse(withImages, { async: false }) as string;
	return DOMPurify.sanitize(html, {
		ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'b', 'i', 'u', 's', 'code', 'pre', 'blockquote', 'ul', 'ol', 'li', 'a', 'img',
			'h1', 'h2', 'h3', 'h4', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'span', 'div', 'sup', 'sub'],
		ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'class', 'target', 'rel'],
		ALLOWED_URI_REGEXP: /^(?:https?:|mailto:|blob:|\/)/i
	});
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
