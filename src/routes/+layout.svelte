<script lang="ts">
	import { onMount, setContext } from 'svelte';
	import { Toaster } from 'svelte-sonner';
	import { goto } from '$app/navigation';
	import { config, mobile, user, WEBUI_NAME } from '$lib/stores';
	import { getBackendConfig } from '$lib/apis';
	import { getSessionUser } from '$lib/apis/auths';
	import i18n, { initI18n } from '$lib/i18n';

	import '../tailwind.css';
	import '../app.css';

	setContext('i18n', i18n);

	// The confidential shell replaces Open WebUI's stock sidebar, so it owns
	// the responsive breakpoint state used by Chat's mobile menu control.
	onMount(() => {
		// Older Google OAuth clients may finish at `/#auth` (or `/auth#auth`).
		// It is a legacy marker, never a route: remove it and let this layout
		// initialize the newly issued same-origin session cookie at the chat root.
		if (window.location.hash === '#auth') {
			window.history.replaceState(
				window.history.state,
				'',
				`${window.location.pathname}${window.location.search}`
			);
		}

		const query = window.matchMedia('(max-width: 767px)');
		const sync = () => mobile.set(query.matches);
		sync();
		query.addEventListener('change', sync);
		return () => query.removeEventListener('change', sync);
	});

	onMount(async () => {
		initI18n(localStorage?.locale);
		try {
			const backendConfig = await getBackendConfig();
			config.set(backendConfig);
			WEBUI_NAME.set(backendConfig?.name ?? 'Open WebUI');
			const cookieToken = document.cookie
				.split('; ')
				.find((cookie) => cookie.startsWith('token='))
				?.slice('token='.length);
			const sessionToken = localStorage.token || cookieToken;

			if (sessionToken) {
				const sessionUser = await getSessionUser(sessionToken).catch(() => null);
				if (sessionUser && !localStorage.token) {
					localStorage.token = sessionToken;
				}
				if (sessionUser) user.set(sessionUser);
				else {
					localStorage.removeItem('token');
					user.set(null);
				}
			} else {
				user.set(null);
			}
		} catch (error) {
			console.error('Confidential Open WebUI could not initialize:', error);
			await goto('/error');
		}
	});
</script>

<svelte:head>
	<title>{$WEBUI_NAME}</title>
	<meta name="description" content="Confidential Open WebUI — browser-local conversations" />
</svelte:head>

<Toaster position="top-center" />
<slot />
