<script lang="ts">
	import { goto } from '$app/navigation';
	import { getModels } from '$lib/apis';
	import { models, user, showSettings } from '$lib/stores';
	import { isConfidentialModel } from '$lib/confidential/client';
	import VerificationCenter from '$lib/components/chat/VerificationCenter.svelte';
	import ConfidentialSidebar from '$lib/components/layout/ConfidentialSidebar.svelte';
	import VerificationProcess from '$lib/components/chat/VerificationProcess.svelte';
	import SettingsModal from '$lib/components/chat/SettingsModal.svelte';

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

<div class="app adverserial-ui relative">
	<ConfidentialSidebar />
	<main id="main-content" class="min-h-screen md:ml-[17.5rem]">
		<slot />
	</main>
	<VerificationProcess />
	<VerificationCenter />
	<SettingsModal bind:show={$showSettings} />
</div>

<style>
	:global(.adverserial-ui) {
		--brand-paper: #d8dadd;
		--brand-ink: #191b1d;
		--brand-dark: #151719;
		--brand-raised: #1d2023;
		--brand-line: rgb(216 218 221 / 0.14);
		--brand-muted: #a0a8b2;
		color: var(--brand-paper);
		background: var(--brand-dark);
		font-family: 'Inter', ui-sans-serif, system-ui, sans-serif;
	}
	:global(.adverserial-ui #main-content) {
		position: relative;
		min-height: 100dvh;
		background-color: var(--brand-dark);
		background-image:
			linear-gradient(rgb(216 218 221 / 0.035) 1px, transparent 1px),
			linear-gradient(90deg, rgb(216 218 221 / 0.035) 1px, transparent 1px);
		background-size: 42px 42px;
		color: var(--brand-paper);
	}
	:global(.adverserial-ui #chat-container) {
		background: transparent !important;
	}
	:global(.adverserial-ui #chat-pane) {
		background: transparent;
	}
	:global(.adverserial-ui #messages-container) {
		scrollbar-color: #66707a transparent;
	}
	:global(.adverserial-ui #message-input-container) {
		border-color: rgb(216 218 221 / 0.24) !important;
		border-radius: 0 !important;
		background: #202326 !important;
		box-shadow: 12px 12px 0 rgb(0 0 0 / 0.12) !important;
	}
	:global(.adverserial-ui #message-input-container textarea) {
		color: var(--brand-paper) !important;
	}
	:global(.adverserial-ui #message-input-container textarea::placeholder) {
		color: #8f98a3 !important;
	}
	:global(.adverserial-ui #messages-container > div) {
		max-width: 72rem;
		margin-inline: auto;
	}
	:global(.modal:has(.adverserial-settings-modal)) {
		background: rgb(7 9 10 / 0.78) !important;
	}
	:global(.adversarial-settings-modal),
	:global(.adverserial-settings-modal) {
		border-color: rgb(216 218 221 / 0.28) !important;
		border-radius: 0 !important;
		background-color: #181a1c !important;
		background-image:
			linear-gradient(rgb(216 218 221 / 0.035) 1px, transparent 1px),
			linear-gradient(90deg, rgb(216 218 221 / 0.035) 1px, transparent 1px) !important;
		background-size: 30px 30px !important;
		color: var(--brand-paper) !important;
		font-family: Inter, ui-sans-serif, system-ui, sans-serif !important;
	}
	:global(.adverserial-settings-modal nav) {
		border-color: rgb(216 218 221 / 0.16) !important;
		background: rgb(20 22 24 / 0.86);
	}
	:global(.adverserial-settings-modal button) {
		border-radius: 0 !important;
	}
	:global(.adverserial-ui .verification-center-drawer),
	:global(.adverserial-ui .process-modal) {
		border-color: rgb(216 218 221 / 0.26) !important;
		border-radius: 0 !important;
		background: #181a1c !important;
		box-shadow: -18px 0 0 rgb(0 0 0 / 0.12) !important;
	}
	:global(.adverserial-ui .verification-center-drawer header),
	:global(.adverserial-ui .process-modal header) {
		border-color: rgb(216 218 221 / 0.18) !important;
		background: #181a1c !important;
	}
	:global(.adverserial-ui .verification-center-drawer h1),
	:global(.adverserial-ui .verification-center-drawer h2),
	:global(.adverserial-ui .process-modal h1),
	:global(.adverserial-ui .process-modal h2) {
		letter-spacing: -0.035em;
	}
	:global(.adverserial-ui .verification-center-drawer code),
	:global(.adverserial-ui .process-modal code) {
		border-radius: 0;
		font-family: 'JetBrains Mono', ui-monospace, monospace;
	}
	:global(.adverserial-ui button) {
		transition-duration: 140ms;
	}
	@media (max-width: 767px) {
		:global(.adverserial-ui #main-content) {
			background-size: 30px 30px;
		}
	}
</style>
