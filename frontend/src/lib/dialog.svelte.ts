/** One confirm dialog for the whole app, asked for from anywhere:
 *   const reason = await dialog.ask({ title, text, reason: 'required' });
 * resolves to the typed reason ('' when no reason field), or null when cancelled.
 * The <ConfirmDialog> in the root layout renders whatever is pending here. Replaces
 * window.prompt(): a prompt cannot show a warning, cannot mark the reason as required, and
 * looks like a browser bug next to a page that imitates fuw.edu.pl. */
export interface DialogRequest {
	title: string;
	text: string;                       // plain text, may contain \n
	confirm?: string;                   // button label, default 'Potwierdź'
	danger?: boolean;                   // red confirm button
	reason?: 'none' | 'optional' | 'required';
	placeholder?: string;
}
interface Pending extends DialogRequest { resolve: (v: string | null) => void }

let pending = $state<Pending | null>(null);

export const dialog = {
	get current() { return pending; },
	ask(req: DialogRequest): Promise<string | null> {
		pending?.resolve(null); // a second ask replaces the first
		return new Promise((resolve) => { pending = { reason: 'none', ...req, resolve }; });
	},
	close(value: string | null) {
		const p = pending;
		pending = null;
		p?.resolve(value);
	}
};
