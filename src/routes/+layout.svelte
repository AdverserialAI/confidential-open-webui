<script lang="ts">
	import { onMount, setContext } from 'svelte';
	import { Toaster } from 'svelte-sonner';
	import { goto } from '$app/navigation';
	import { config, user, WEBUI_NAME } from '$lib/stores';
	import { getBackendConfig } from '$lib/apis';
	import { getSessionUser } from '$lib/apis/auths';
	import i18n, { initI18n } from '$lib/i18n';

	import '../tailwind.css';
	import '../app.css';

	setContext('i18n', i18n);

	onMount(async () => {
		initI18n(localStorage?.locale);
		try {
			const backendConfig = await getBackendConfig();
			config.set(backendConfig);
			WEBUI_NAME.set(backendConfig?.name ?? 'Open WebUI');
			if (localStorage.token) {
				const sessionUser = await getSessionUser(localStorage.token).catch(() => null);
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
