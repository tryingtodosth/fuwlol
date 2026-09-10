// Ambient declarations for third-party modules that ship no types.
// This file must stay a non-module (no import/export) so these are global, not augmentations.
// Third-party modules that ship no type declarations.
declare module 'latex.js' {
	export class HtmlGenerator {
		constructor(options?: { hyphenate?: boolean; documentClass?: unknown; styles?: string[] });
		domFragment(): DocumentFragment;
		stylesAndScripts(base?: string): DocumentFragment;
	}
	export function parse(src: string, options: { generator: HtmlGenerator }): HtmlGenerator;
}
declare module 'katex/contrib/auto-render' {
	interface Delimiter { left: string; right: string; display: boolean }
	interface Options { delimiters?: Delimiter[]; throwOnError?: boolean; ignoredTags?: string[]; errorColor?: string }
	const renderMathInElement: (el: HTMLElement, options?: Options) => void;
	export default renderMathInElement;
}
declare module 'katex/dist/katex.min.css';
