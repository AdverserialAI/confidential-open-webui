<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { getSessionUser } from '$lib/apis/auths';

	type BillingDestination = 'account' | 'foothold' | 'hacker_manifesto' | 'godmod3';
	const MEMBERSHIP_DESTINATIONS = new Set<Exclude<BillingDestination, 'account'>>([
		'foothold',
		'hacker_manifesto',
		'godmod3'
	]);

	let error = '';

	const destinationFor = (plan: string | null): BillingDestination | null => {
		if (plan === null) return 'account';
		return MEMBERSHIP_DESTINATIONS.has(plan as Exclude<BillingDestination, 'account'>)
			? (plan as Exclude<BillingDestination, 'account'>)
			: null;
	};

	const isCompactJws = (value: unknown): value is string =>
		typeof value === 'string' &&
		value.length > 32 &&
		value.length <= 4096 &&
		/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(value);

	onMount(async () => {
		const plan = $page.url.searchParams.get('plan');
		const destination = destinationFor(plan);
		if (!destination) {
			error = 'This membership plan is not available. Please choose a plan again.';
			return;
		}

		const localDestination = `/billing${plan ? `?plan=${encodeURIComponent(plan)}` : ''}`;
		const signIn = () => goto(`/auth?redirect=${encodeURIComponent(localDestination)}`, { replaceState: true });
		const session = await getSessionUser().catch(() => null);
		if (!session) {
			await signIn();
			return;
		}

		let handoff = '';
		try {
			const response = await fetch('/api/v1/confidential/billing-handoff', {
				method: 'POST',
				credentials: 'include',
				headers: { 'content-type': 'application/json', accept: 'application/json' },
				body: JSON.stringify({ destination })
			});
			const payload = await response.json().catch(() => null);
			if (!response.ok || !isCompactJws(payload?.handoff)) {
				throw new Error('Secure billing handoff could not be created.');
			}
			handoff = payload.handoff;
		} catch {
			error = 'We could not securely connect your account to billing. Please try again.';
			return;
		}

		// This must be a top-level navigation. Billing sets its own host-only
		// session cookie after atomically consuming the one-time assertion; no
		// Open WebUI credential or browser session token crosses the origin.
		const form = document.createElement('form');
		form.method = 'POST';
		form.action = 'https://billing.adverserial.ai/account/session/exchange';
		const input = document.createElement('input');
		input.type = 'hidden';
		input.name = 'handoff';
		input.value = handoff;
		form.appendChild(input);
		document.body.appendChild(form);
		form.submit();
	});
</script>

<svelte:head>
	<title>Continue to billing — Adverserial AI</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<main class="min-h-screen flex items-center justify-center px-6 bg-white dark:bg-gray-950">
	<div class="max-w-md text-center space-y-4">
		<h1 class="text-2xl font-semibold">{error ? 'Unable to continue' : 'Connecting your account'}</h1>
		<p class="text-gray-600 dark:text-gray-300" role="status">
			{error || 'Taking you securely to billing. Please keep this page open.'}
		</p>
		{#if error}
			<a class="underline block" href={'/auth?redirect=' + encodeURIComponent($page.url.pathname + $page.url.search)}
				>Sign in again</a
			>
			<a class="underline block" href="https://billing.adverserial.ai/membership">View memberships</a>
		{/if}
	</div>
</main>
