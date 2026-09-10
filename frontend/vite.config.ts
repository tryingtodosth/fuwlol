import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
			},
			// A pure SPA: every route is served from 200.html (see deploy/OVH.md for the rewrite).
			adapter: adapter({ fallback: '200.html', strict: false })
		})
	]
});
