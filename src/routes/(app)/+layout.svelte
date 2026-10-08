<script lang="ts">
	import { goto } from '$app/navigation';
	import { getModels } from '$lib/apis';
	import { models, user } from '$lib/stores';
	import { isConfidentialModel } from '$lib/confidential/client';
	import VerificationCenter from '$lib/components/chat/VerificationCenter.svelte';
	import VerificationProcess from '$lib/components/chat/VerificationProcess.svelte';

	let modelsLoadedFor = '';
	let redirecting = false;

	const loadModels = async (userId: string) => {
		try {
			// This browser may select only confidential transports. A model that is
			// not explicitly registered as confidential never reaches Chat.svelte.
			models.set((await getModels(localStorage.token)).filter(isConfidentialModel));
			modelsLoadedFor = userId;
		} catch (error) {
			console.error('Could not load confidential model access:', error);
		}
	};

	$: if ($user === null && !redirecting) {
		redirecting = true;
		void goto('/auth?redirect=%2F');
	}
	$: if ($user?.id && modelsLoadedFor !== $user.id) void loadModels($user.id);
</script>

<div class="app relative">
	<main id="main-content" class="min-h-screen bg-white text-gray-900 dark:bg-gray-950 dark:text-gray-100">
		<slot />
	</main>
	<VerificationProcess />
	<VerificationCenter />
</div>
