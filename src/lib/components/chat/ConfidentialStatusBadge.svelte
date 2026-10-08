<script lang="ts">
	import { onMount } from 'svelte';
	import LockClosed from '$lib/components/icons/LockClosed.svelte';
	import { confidentialVerificationConfig } from '$lib/confidential/verification';

	export let model: { id?: string; info?: { meta?: Record<string, unknown> } } | null = null;

	let localPreview = false;
	$: verificationConfig = confidentialVerificationConfig(model);
	$: visible = verificationConfig !== null || localPreview;

	onMount(() => {
		localPreview = ['127.0.0.1', 'localhost'].includes(window.location.hostname);
	});

	const openVerificationCenter = () => {
		window.dispatchEvent(new Event('adverserial:open-verification-process'));
	};
</script>

{#if visible}
	<button
		type="button"
		on:click={openVerificationCenter}
		aria-label="Open runtime verification"
		class="inline-flex h-[1.875rem] shrink-0 items-center gap-1.5 rounded-lg border border-[#3a424e] bg-[#282e38] px-2 text-[0.625rem] font-medium tracking-[0.045em] text-[#d5d8da] transition hover:border-[#91b5a4]/55 hover:text-white dark:bg-[#282e38]"
	>
		<span class="flex size-4 items-center justify-center rounded border border-[#91b5a4]/25 bg-[#91b5a4]/[0.07] text-[#a1c4b3]"><LockClosed className="size-2.5" strokeWidth="2" /></span>
		<span class="hidden sm:inline">{verificationConfig ? 'Verify runtime' : 'Verification preview'}</span>
	</button>
{/if}
