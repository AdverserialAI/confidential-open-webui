<script lang="ts">
	import { goto } from '$app/navigation';
	import { getModels } from '$lib/apis';
	import { models, user } from '$lib/stores';

	let modelsLoadedFor = '';
	let redirecting = false;

	const loadModels = async (userId: string) => {
		try {
			models.set(await getModels(localStorage.token));
			modelsLoadedFor = userId;
		} catch (error) {
			console.error('Could not load confidential model access:', error);
		}
	};

	// `undefined` means the root layout is still resolving the browser session.
	// Redirect only after the auth check has positively returned `null`.
	$: if ($user === null && !redirecting) {
		redirecting = true;
		void goto('/auth?redirect=%2F');
	}
	$: if ($user?.id && modelsLoadedFor !== $user.id) void loadModels($user.id);
</script>

<main id="main-content" class="min-h-screen bg-white text-gray-900 dark:bg-gray-950 dark:text-gray-100">
	<slot />
</main>
