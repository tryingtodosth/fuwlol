<script lang="ts">
	/** The thin grey strip at the bottom, small grey text — like the faculty site's. */
</script>

<footer class="foot">
	<div class="container foot__in">
		<p>
			fuw.lol — nieoficjalne archiwum Wydziału Fizyki UW. Zgłoś błąd / prośbę o usunięcie: przy każdym
			wpisie. Ta strona nie jest stroną Wydziału.
		</p>
		<p><a href="/o-archiwum">O archiwum</a></p>
	</div>
</footer>

<style>
	.foot {
		border-top: 1px solid var(--line);
		background: var(--box);
		margin-top: 20px;
	}
	.foot__in {
		padding: 10px 0 14px;
		display: flex;
		gap: 12px;
		justify-content: space-between;
		flex-wrap: wrap;
	}
	.foot p {
		margin: 0;
		font-size: 11px;
		color: var(--muted);
	}
	.foot :global(a) {
		color: var(--muted);
		text-decoration: underline;
	}
</style>
