// A pure SPA: LaTeX.js, marked and KaTeX all need a browser, and every page's data comes
// from the API at runtime, so there is nothing to render or prerender on a server.
export const ssr = false;
export const prerender = false;
