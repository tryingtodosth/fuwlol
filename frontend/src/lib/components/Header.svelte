<script lang="ts">
	/** The faculty banner and the green bar, copied from www.fuw.edu.pl on purpose. */
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { auth } from '$lib/auth.svelte';
	import type { Category } from '$lib/types';

	let categories = $state<Category[]>([]);
	let pending = $state(0);
	let dropOpen = $state(false);
	let mobileOpen = $state(false);

	onMount(async () => {
		try {
			categories = await api.get<Category[]>('/categories/');
		} catch {
			/* the rest of the navigation still works without the category list */
		}
	});

	// plain `let`, not $state: only a guard, never read by the template
	let askedForStats = false;
	$effect(() => {
		if (!auth.isStaff || askedForStats) return;
		askedForStats = true;
		api.get<{ pending: number }>('/posts/stats/')
			.then((s) => (pending = s.pending))
			.catch(() => {});
	});

	// any navigation closes whatever the reader left open
	$effect(() => {
		void page.url.pathname;
		void page.url.search;
		dropOpen = false;
		mobileOpen = false;
	});

	async function logout() {
		await auth.logout();
		goto('/');
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape') dropOpen = false;
	}
</script>

<svelte:window onkeydown={onKey} />

<div class="banner">
	<div class="container banner__in">
		<a class="brand" href="/">
			<svg class="brand__mark" width="46" height="46" viewBox="0 0 46 46" aria-hidden="true">
				<rect width="46" height="46" fill="#175e4c" />
				<polygon points="23,6 42,17 4,17" fill="#fff" />
				<rect x="6" y="19" width="5" height="15" fill="#fff" />
				<rect x="14" y="19" width="5" height="15" fill="#fff" />
				<rect x="27" y="19" width="5" height="15" fill="#fff" />
				<rect x="35" y="19" width="5" height="15" fill="#fff" />
				<rect x="3" y="35" width="40" height="4" fill="#fff" />
			</svg>
			<span class="brand__txt">
				<span class="brand__name">fuw.lol</span>
				<span class="brand__sub">ARCHIWUM WYDZIAŁU FIZYKI UW</span>
			</span>
		</a>

		<div class="banner__icons">
			<a class="icon" href="/przegladaj" title="Szukaj w archiwum" aria-label="Szukaj w archiwum">
				<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
					<circle cx="7.5" cy="7.5" r="5.2" fill="none" stroke="#175e4c" stroke-width="2" />
					<line x1="11.4" y1="11.4" x2="16.5" y2="16.5" stroke="#175e4c" stroke-width="2" />
				</svg>
			</a>
			{#if auth.isAuthenticated}
				<a class="who" href="/konto">{auth.user?.username}</a>
				<button type="button" class="linky" onclick={logout}>Wyloguj</button>
			{:else if auth.ready}
				<a class="who" href="/logowanie">Zaloguj się</a>
			{/if}
		</div>
	</div>
</div>

<button
	type="button"
	class="toggleMenu"
	aria-expanded={mobileOpen}
	aria-controls="nav-main"
	onclick={() => (mobileOpen = !mobileOpen)}
>
	Menu
</button>

<nav class="nav" class:is-open={mobileOpen} id="nav-main" aria-label="Nawigacja główna">
	<ul class="container nav__list">
		<li><a href="/">Strona główna</a></li>
		<li class="has-drop">
			<button
				type="button"
				aria-expanded={dropOpen}
				aria-haspopup="true"
				onclick={() => (dropOpen = !dropOpen)}
			>
				Przeglądaj <span class="arr" aria-hidden="true">▾</span>
			</button>
			<ul class="drop" class:is-open={dropOpen}>
				<li><a href="/przegladaj">Wszystkie wpisy</a></li>
				{#each categories as c (c.slug)}
					<li>
						<a href="/przegladaj?category={c.slug}">
							{c.emoji} {c.name} <span class="cnt">({c.post_count})</span>
						</a>
					</li>
				{/each}
			</ul>
		</li>
		<li><a href="/ludzie">Ludzie</a></li>
		<li><a href="/os-czasu">Oś czasu</a></li>
		<li><a href="/losowe">Losowy wpis</a></li>
		<li><a href="/czat">Czat</a></li>
		<li><a href="/dodaj">Dodaj wpis</a></li>
		{#if auth.isAuthenticated}
			<li><a href="/moje">Moje wpisy</a></li>
		{/if}
		{#if auth.user?.is_trusted}
			<li><a href="/tablica">Tablica</a></li>
		{/if}
		{#if auth.isStaff}
			<li>
				<a href="/moderacja">Moderacja{pending ? ` (${pending})` : ''}</a>
			</li>
		{/if}
		<li><a href="/o-archiwum">O archiwum</a></li>
	</ul>
</nav>

<style>
	.banner {
		background: var(--banner);
		border-bottom: 1px solid #bbb;
	}
	.banner__in {
		min-height: 70px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 10px;
		color: #222;
	}
	.brand:hover {
		text-decoration: none;
	}
	.brand__mark {
		display: block;
		flex: 0 0 auto;
	}
	.brand__txt {
		display: block;
		line-height: 1.2;
	}
	.brand__name {
		display: block;
		font-size: 22px;
		font-weight: bold;
		color: #175e4c;
		letter-spacing: -0.5px;
	}
	.brand__sub {
		display: block;
		font-size: 10px;
		letter-spacing: 1px;
		color: #555;
	}
	.banner__icons {
		display: flex;
		align-items: center;
		gap: 10px;
		font-size: 11px;
	}
	.banner__icons a {
		color: #444;
	}
	.icon {
		display: inline-flex;
		padding: 2px;
	}
	.who {
		max-width: 130px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.linky {
		background: none;
		border: 0;
		padding: 0;
		font-size: 11px;
		color: var(--rust);
		cursor: pointer;
		font-family: inherit;
	}
	.linky:hover {
		background: none;
		text-decoration: underline;
	}

	/* the grey "Menu" bar, only on phones — .toggleMenu on the faculty site */
	.toggleMenu {
		display: none;
		width: 100%;
		background: #666;
		border: 0;
		color: #fff;
		font-size: 13px;
		padding: 8px 12px;
		text-align: left;
		border-radius: 0;
	}
	.toggleMenu:hover {
		background: #777;
	}

	.nav {
		background: var(--green);
	}
	.nav__list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
	}
	.nav__list > li {
		position: relative;
	}
	.nav :global(a),
	.nav button {
		display: block;
		color: #fff;
		font-size: 13px;
		line-height: 1.3;
		padding: 7px 12px;
		background: none;
		border: 0;
		font-family: inherit;
		cursor: pointer;
		white-space: nowrap;
		border-radius: 0;
	}
	.nav :global(a:hover),
	.nav button:hover,
	.has-drop:hover > button,
	.has-drop:focus-within > button {
		background: var(--green-light);
		text-decoration: none;
	}
	.arr {
		font-size: 10px;
	}
	.drop {
		display: none;
		position: absolute;
		left: 0;
		top: 100%;
		z-index: 40;
		min-width: 230px;
		list-style: none;
		margin: 0;
		padding: 3px 0;
		background: var(--green);
		border: 1px solid var(--green-dark);
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.25);
	}
	.has-drop:hover .drop,
	.has-drop:focus-within .drop,
	.drop.is-open {
		display: block;
	}
	.cnt {
		color: #b7ddd1;
		font-size: 11px;
	}

	@media (max-width: 850px) {
		.toggleMenu {
			display: block;
		}
		.nav {
			display: none;
		}
		.nav.is-open {
			display: block;
		}
		.nav__list {
			display: block;
		}
		.nav__list > li {
			border-top: 1px solid var(--green-dark);
		}
		.drop {
			position: static;
			border: 0;
			box-shadow: none;
			background: var(--green-dark);
		}
		.brand__name {
			font-size: 18px;
		}
		.brand__sub {
			font-size: 9px;
		}
	}
</style>
