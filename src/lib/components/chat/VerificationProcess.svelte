<script lang="ts">
	import { onMount } from 'svelte';
	import LockClosed from '$lib/components/icons/LockClosed.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import DocumentCheck from '$lib/components/icons/DocumentCheck.svelte';

	let open = false;
	let localPreview = false;

	onMount(() => {
		localPreview = ['127.0.0.1', 'localhost'].includes(window.location.hostname);
		const openProcess = () => (open = true);
		window.addEventListener('adverserial:open-verification-process', openProcess);
		return () => window.removeEventListener('adverserial:open-verification-process', openProcess);
	});

	const openCenter = () => {
		open = false;
		window.dispatchEvent(new Event('adverserial:open-verification-center'));
	};
</script>

<svelte:window on:keydown={(event) => event.key === 'Escape' && (open = false)} />

{#if open}
	<div class="fixed inset-0 z-[70] flex items-center justify-center p-4 sm:p-8" aria-live="polite">
		<button type="button" class="absolute inset-0 h-full w-full bg-black/70" on:click={() => (open = false)} aria-label="Close verification process"></button>
		<section class="process-modal relative w-full max-w-[680px] overflow-hidden rounded-2xl border border-[#3a424e] bg-[#202224] text-[#edf0f5] shadow-2xl shadow-black/70" role="dialog" aria-modal="true" aria-labelledby="verification-process-title">
			<header class="flex items-start justify-between gap-4 border-b border-[#343a44] px-6 py-5 sm:px-7">
				<div class="flex items-start gap-3">
					<div class="brand-mark">A</div>
					<div>
						<p class="text-[0.625rem] font-medium tracking-[0.15em] text-[#b9d5c8]">ADVERSERIAL AI · CONFIDENTIAL INFERENCE</p>
						<h2 id="verification-process-title" class="mt-1.5 text-xl font-semibold tracking-tight text-white">Verification process</h2>
					</div>
				</div>
				<button type="button" class="flex size-8 shrink-0 items-center justify-center rounded-md text-lg text-[#a7b1c0] transition hover:bg-white/[0.06] hover:text-white" on:click={() => (open = false)} aria-label="Close verification process">×</button>
			</header>

			<div class="px-6 py-5 sm:px-7 sm:py-6">
				<p class="max-w-[590px] text-[0.95rem] leading-7 text-[#d6dce5]">
					{#if localPreview}
						Privacy needs proof, not a badge. This preview maps the browser-side checks that must complete before a confidential runtime can be represented as verified.
					{:else}
						The browser independently validates a fresh signed receipt for the configured runtime. The verification request contains a one-time nonce, never your prompt or account data.
					{/if}
				</p>

				{#if localPreview}
					<p class="mt-3 rounded-lg border border-[#3a424e] bg-[#1b1d1f] px-3 py-2.5 text-xs leading-5 text-[#a7b1c0]"><strong class="text-[#edf0f5]">Local interface preview.</strong> No encryption, enclave, hardware-attestation, or secure-endpoint claim is made here.</p>
				{/if}

				<section class="process-map mt-7" aria-label="Adverserial verification path">
					<div class="process-map__label"><CheckCircle className="size-3.5" strokeWidth="1.9" /> ATTESTATION PROOF</div>
					<div class="process-map__stage">
						<div class="map-card map-card--browser">
							<div class="map-card__title"><span class="map-card__icon">⌁</span> Adverserial Chat</div>
							<ul><li>Creates a one-time challenge</li><li>Verifies the receipt locally</li></ul>
						</div>
						<div class="map-card map-card--verify">
							<div class="map-card__title"><DocumentCheck className="size-3.5 text-[#a1c4b3]" strokeWidth="1.8" /> Adverserial Verify</div>
							<ul><li>Signs the verification receipt</li><li>Publishes the expected policy</li></ul>
						</div>
						<div class="map-card map-card--runtime">
							<div class="map-card__title"><LockClosed className="size-3.5 text-[#a1c4b3]" strokeWidth="1.8" /> Configured runtime</div>
							<p>Must return fresh hardware evidence bound to the selected model and runtime policy.</p>
						</div>
						<span class="map-line map-line--one" aria-hidden="true"></span><span class="map-line map-line--two" aria-hidden="true"></span><span class="map-line map-line--three" aria-hidden="true"></span>
					</div>
				</section>

				<div class="mt-5 grid gap-2 sm:grid-cols-3" aria-label="Browser-side proof checks">
					<div class="proof-requirement"><span>01</span><strong>Signature</strong><p>Pinned ES256 receipt key</p></div>
					<div class="proof-requirement"><span>02</span><strong>Freshness</strong><p>Nonce, issued and expiry times</p></div>
					<div class="proof-requirement"><span>03</span><strong>Binding</strong><p>Evidence, model, endpoint, policy</p></div>
				</div>

				<div class="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-[#343a44] pt-4">
					<p class="text-xs leading-5 text-[#a7b1c0]">Every proof module stays pending until the browser validates its signed evidence.</p>
					<button type="button" class="process-action" on:click={openCenter}>Open Verification Center</button>
				</div>
			</div>
		</section>
	</div>
{/if}

<style>
	.process-modal { background-image: linear-gradient(rgb(255 255 255 / 0.012) 1px, transparent 1px), linear-gradient(90deg, rgb(255 255 255 / 0.012) 1px, transparent 1px); background-size: 18px 18px; }
	.brand-mark { display: flex; width: 2.15rem; height: 2.15rem; flex: 0 0 auto; align-items: center; justify-content: center; border: 1px solid rgb(145 181 164 / 0.38); border-radius: 0.6rem; background: rgb(145 181 164 / 0.08); color: #b9d5c8; font-size: 0.8rem; font-weight: 700; }
	.process-map { position: relative; border: 1px dashed #626870; border-radius: 0.8rem; background: rgb(27 29 31 / 0.72); padding: 1.3rem; }
	.process-map__label { position: absolute; top: -1.05rem; left: 1rem; display: inline-flex; align-items: center; gap: 0.4rem; border: 1px solid #668775; border-radius: 0.35rem; background: #303640; padding: 0.35rem 0.55rem; color: #b9d5c8; font-size: 0.67rem; font-weight: 600; letter-spacing: 0.06em; }
	.process-map__stage { position: relative; display: grid; min-height: 235px; grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.25fr); grid-template-rows: 1fr 1fr; gap: 1rem; align-items: center; }
	.map-card { position: relative; z-index: 1; border: 1px solid #3a424e; border-radius: 0.55rem; background: #282e38; padding: 0.85rem; box-shadow: 0 10px 25px rgb(0 0 0 / 0.14); }
	.map-card__title { display: flex; align-items: center; gap: 0.45rem; color: #f1f2f3; font-size: 0.83rem; font-weight: 600; }
	.map-card__icon { color: #a1c4b3; }
	.map-card ul { margin: 0.45rem 0 0; padding-left: 1rem; color: #a7b1c0; font-size: 0.72rem; line-height: 1.3rem; }
	.map-card p { margin: 0.45rem 0 0; color: #a7b1c0; font-size: 0.72rem; line-height: 1.3rem; }
	.map-card--browser { grid-row: 2; }
	.map-card--verify { grid-column: 2; grid-row: 1 / span 2; align-self: center; }
	.map-card--runtime { grid-column: 2; grid-row: 2; width: 84%; justify-self: end; border-color: #668775; }
	.map-line { position: absolute; z-index: 0; border-color: #758090; border-style: dashed; opacity: 0.75; }
	.map-line--one { left: 20%; top: 27%; width: 51%; border-top-width: 1px; }
	.map-line--two { left: 20%; top: 28%; height: 45%; width: 50%; border-bottom-width: 1px; border-left-width: 1px; }
	.map-line--three { left: 20%; bottom: 23%; width: 56%; border-top-width: 1px; }
	.proof-requirement { min-height: 4.5rem; border: 1px solid #343a44; border-radius: 0.65rem; background: #282e38; padding: 0.75rem; }
	.proof-requirement span { color: #a1c4b3; font-size: 0.62rem; font-weight: 600; letter-spacing: 0.06em; }
	.proof-requirement strong { display: block; margin-top: 0.25rem; color: #edf0f5; font-size: 0.76rem; font-weight: 600; }
	.proof-requirement p { margin: 0.22rem 0 0; color: #a7b1c0; font-size: 0.68rem; line-height: 1rem; }
	.process-action { display: inline-flex; min-height: 2.3rem; align-items: center; justify-content: center; border: 1px solid #668775; border-radius: 0.5rem; background: #475f53; padding: 0.5rem 0.9rem; color: #edf0f5; font-size: 0.8rem; font-weight: 600; transition: background-color 150ms ease; }
	.process-action:hover { background: #496d5c; }
	@media (max-width: 520px) { .process-map { padding: 1rem; } .process-map__stage { min-height: 0; grid-template-columns: 1fr; grid-template-rows: auto; gap: 0.7rem; } .map-card--browser, .map-card--verify, .map-card--runtime { grid-column: auto; grid-row: auto; width: auto; justify-self: auto; } .map-line { display: none; } }
</style>
