<script lang="ts">
	import { onMount } from 'svelte';
	import { models } from '$lib/stores';
	import LockClosed from '$lib/components/icons/LockClosed.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import DocumentCheck from '$lib/components/icons/DocumentCheck.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import {
		confidentialVerificationConfig,
		type VerificationResult
	} from '$lib/confidential/verification';
	import {
		confidentialRuntime,
		isConfidentialModel,
		verifyConfidentialRuntime
	} from '$lib/confidential/client';

	type VerifiableModel = { id?: string; name?: string; info?: { meta?: Record<string, unknown> } };
	type ModuleName = 'runtime' | 'encryption' | 'code';

	let open = false;
	let localPreview = false;
	let verifying = false;
	let result: VerificationResult | null = null;
	let expandedModule: ModuleName | null = 'runtime';

	$: model = (($models ?? []).find((candidate) => isConfidentialModel(candidate)) ?? null) as VerifiableModel | null;
	$: verificationConfig = confidentialVerificationConfig(model);
	$: liveRuntime = $confidentialRuntime;
	$: simulation = localPreview && !model;
	$: verified = liveRuntime.status === 'verified' || result?.status === 'verified';
	$: failed = liveRuntime.status === 'failed' || result?.status === 'failed';
	$: runtimeFingerprint =
		liveRuntime.status === 'verified'
			? liveRuntime.proof.attestationStateDigest
			: result?.status === 'verified'
				? result.proof.runtimeDigest ?? result.proof.evidenceDigest
				: null;
	$: codeFingerprint =
		liveRuntime.status === 'verified'
			? typeof liveRuntime.policy.model_artifact_digest === 'string'
				? liveRuntime.policy.model_artifact_digest
				: null
			: result?.status === 'verified'
				? result.proof.modelDigest ?? result.proof.runtimeDigest ?? null
				: null;
	$: runtimeStatus = verified ? 'Attested' : failed ? 'Failed' : 'Pending';
	$: encryptionStatus = liveRuntime.status === 'verified' ? 'EHBP bound' : 'Evidence required';
	$: codeStatus = codeFingerprint ? 'Policy bound' : 'Evidence required';

	onMount(() => {
		localPreview = ['127.0.0.1', 'localhost'].includes(window.location.hostname);
		const openCenter = () => (open = true);
		window.addEventListener('adverserial:open-verification-center', openCenter);
		return () => window.removeEventListener('adverserial:open-verification-center', openCenter);
	});

	const verify = async () => {
		if (!model?.id || verifying) return;
		verifying = true;
		try {
			await verifyConfidentialRuntime(model.id, localStorage.token);
			result = null;
		} catch {
			// The shared runtime store carries the safe, user-visible failure reason.
		}
		verifying = false;
		expandedModule = 'runtime';
	};

	const toggle = (module: ModuleName) => {
		expandedModule = expandedModule === module ? null : module;
	};

	const openFromFab = () => (open = true);
</script>

<svelte:window on:keydown={(event) => event.key === 'Escape' && (open = false)} />

<button
	type="button"
	class="verify-fab fixed bottom-5 right-5 z-[60] inline-flex items-center gap-2 rounded-full border border-[#3a424e] bg-[#202224]/95 px-3 py-2 text-xs font-medium text-[#edf0f5] shadow-2xl shadow-black/40 transition hover:border-[#91b5a4]/50 hover:bg-[#282e38] focus:outline-none focus:ring-2 focus:ring-[#91b5a4]/60"
	on:click={openFromFab}
	aria-haspopup="dialog"
	aria-expanded={open}
	aria-label="Open Verification Center"
>
	<span class="relative flex size-5 items-center justify-center rounded-full border border-[#91b5a4]/35 bg-[#91b5a4]/10 text-[#b9d5c8]"><LockClosed className="size-3" strokeWidth="2" /></span>
	<span class="tracking-[0.08em]">VERIFY</span>
	<span class="size-1.5 rounded-full {verified ? 'bg-[#91b5a4]' : failed ? 'bg-[#dd8888]' : 'bg-[#aaaeb3]'}" aria-hidden="true"></span>
</button>

{#if open}
	<div class="fixed inset-0 z-[70]" aria-live="polite">
		<button type="button" class="absolute inset-0 h-full w-full bg-black/55" on:click={() => (open = false)} aria-label="Close Verification Center"></button>
		<aside class="verification-center-drawer verification-modal absolute inset-y-0 right-0 flex h-dvh w-full max-w-[480px] flex-col overflow-y-auto border-l border-[#3a424e] bg-[#202224] text-[#edf0f5] shadow-2xl shadow-black/70" role="dialog" aria-modal="true" aria-labelledby="verification-center-title">
			<header class="flex items-start justify-between gap-5 border-b border-[#343a44] px-6 py-5 sm:px-7">
				<div>
					<p class="text-[0.625rem] font-medium tracking-[0.15em] text-[#b9d5c8]">ADVERSERIAL AI · CONFIDENTIAL RUNTIME</p>
					<h2 id="verification-center-title" class="mt-2 text-xl font-semibold tracking-tight text-white">Verification Center</h2>
					<p class="mt-1 text-xs text-[#a7b1c0]">Powered by Adverserial Verify · checked in your browser.</p>
				</div>
				<button type="button" class="flex size-8 shrink-0 items-center justify-center rounded-md text-lg text-[#a7b1c0] transition hover:bg-white/[0.06] hover:text-white" on:click={() => (open = false)} aria-label="Close Verification Center">×</button>
			</header>

			<div class="flex-1 px-6 pb-6 pt-5 sm:px-7 sm:pb-7">
				<section class="summary-card">
					<p class="text-sm leading-6 text-[#e5ebf2]">
						{#if verified}
							The signed runtime receipt is valid for the configured model and policy. Each module below reports exactly what this browser established.
						{:else if failed}
							The latest receipt did not establish a trusted runtime. The reason is shown in Runtime is isolated; no module is treated as verified.
						{:else if simulation}
							This local preview shows the evidence users will inspect once a confidential inference endpoint is connected.
						{:else if model}
							Request a fresh receipt to verify the runtime signature, evidence binding, freshness, model, endpoint, and configured policy.
						{:else}
							No active model currently publishes confidential-runtime verification metadata.
						{/if}
					</p>
					{#if simulation}
						<p class="mt-3 rounded-lg border border-[#3a424e] bg-[#1b1d1f] px-3 py-2.5 text-xs leading-5 text-[#a7b1c0]"><strong class="text-[#edf0f5]">Local UI simulation.</strong> This page does not make a claim about encryption, an enclave, hardware attestation, or a secure inference endpoint.</p>
					{:else if failed}
						<p class="mt-3 rounded-lg border border-[#6e4e4e] bg-[#2a1c1d] px-3 py-2.5 text-xs leading-5 text-[#f0c4c4]">{liveRuntime.status === 'failed' ? liveRuntime.reason : result && result.status === 'failed' ? result.reason : 'Runtime verification failed.'}</p>
					{/if}
				</section>

				<section class="mt-5 space-y-2" aria-label="Verification modules">
					<div class="verification-module">
						<button type="button" class="module-header" aria-expanded={expandedModule === 'runtime'} on:click={() => toggle('runtime')}>
							<span class="module-icon"><LockClosed className="size-4" strokeWidth="1.8" /></span><span class="min-w-0 flex-1 text-left"><strong>Runtime is isolated</strong><small>Hardware evidence, receipt signature, freshness, and policy binding</small></span><span class:verified-state={verified} class:failed-state={failed} class="module-state">{runtimeStatus}</span><span class="module-chevron">{expandedModule === 'runtime' ? '⌃' : '⌄'}</span>
						</button>
						{#if expandedModule === 'runtime'}
							<div class="module-detail">
								{#if liveRuntime.status === 'verified'}
									<p>The browser verified Intel TDX and NVIDIA evidence, the signed policy, the fresh quote-bound key, and the configured model before enabling confidential inference.</p>
									<div class="fingerprint"><span>Attestation-state fingerprint</span><strong>{runtimeFingerprint}</strong><em>Attested ✓</em></div>
									<dl class="evidence-list"><div><dt>Hardware verifier</dt><dd>{liveRuntime.proof.hardwareVerifier ?? 'Phala TDX + NVIDIA'}</dd></div><div><dt>TEE</dt><dd>{liveRuntime.proof.tee ?? 'Intel TDX'}</dd></div><div><dt>GPU evidence</dt><dd>{liveRuntime.proof.gpu ?? 'NVIDIA CC'}</dd></div><div><dt>Valid until</dt><dd>{new Date(liveRuntime.proof.expiresEpoch * 1000).toISOString()}</dd></div></dl>
								{:else if result?.status === 'verified'}
									<p>The browser verified the receipt’s ES256 signature with a pinned key, its fresh nonce, expiration, signed evidence digest, selected model, endpoint, and runtime policy.</p>
									<div class="fingerprint"><span>Enclave/runtime fingerprint</span><strong>{runtimeFingerprint}</strong><em>Attested ✓</em></div>
									<dl class="evidence-list"><div><dt>Receipt signing key</dt><dd>ES256 · {result.proof.receiptKeyId}</dd></div><div><dt>Receipt fingerprint</dt><dd>{result.proof.receiptDigest}</dd></div><div><dt>Evidence fingerprint</dt><dd>{result.proof.evidenceDigest}</dd></div><div><dt>Valid until</dt><dd>{result.proof.expiresAt}</dd></div></dl>
								{:else}
									<p>A production verifier must return fresh hardware evidence plus a signed receipt bound to this browser’s one-time nonce. {failed ? 'The latest receipt failed validation.' : 'No receipt has been validated yet.'}</p>
								{/if}
							</div>
						{/if}
					</div>

					<div class="verification-module">
						<button type="button" class="module-header" aria-expanded={expandedModule === 'encryption'} on:click={() => toggle('encryption')}>
							<span class="module-icon"><span class="text-sm">⌁</span></span><span class="min-w-0 flex-1 text-left"><strong>Data is encrypted</strong><small>Per-request end-to-end encryption and recipient key binding</small></span><span class="module-state">{encryptionStatus}</span><span class="module-chevron">{expandedModule === 'encryption' ? '⌃' : '⌄'}</span>
						</button>
						{#if expandedModule === 'encryption'}
							<div class="module-detail"><p>{liveRuntime.status === 'verified' ? 'Each request is encrypted with EHBP to the recipient key that the verified runtime bound to its fresh evidence. The relay receives ciphertext and the one-use entitlement, never the prompt or completion.' : 'This module becomes verified only after the browser validates a signed recipient-key fingerprint and protocol binding for the active session.'}</p><p class="detail-note">The verification check itself sends a one-time nonce only; it does not send a prompt or account data.</p></div>
						{/if}
					</div>

					<div class="verification-module">
						<button type="button" class="module-header" aria-expanded={expandedModule === 'code'} on:click={() => toggle('code')}>
							<span class="module-icon"><DocumentCheck className="size-4" strokeWidth="1.8" /></span><span class="min-w-0 flex-1 text-left"><strong>Code is auditable</strong><small>Model/runtime artifact identity and published provenance</small></span><span class:verified-state={Boolean(codeFingerprint)} class="module-state">{codeStatus}</span><span class="module-chevron">{expandedModule === 'code' ? '⌃' : '⌄'}</span>
						</button>
						{#if expandedModule === 'code'}
							<div class="module-detail">
								{#if codeFingerprint}
									<p>The receipt binds this runtime to the configured artifact policy. That identity check is verified independently from the hardware receipt.</p><div class="fingerprint"><span>Configured artifact fingerprint</span><strong>{codeFingerprint}</strong><em>Policy-bound ✓</em></div>
								{:else}
									<p>This module requires a signed model or runtime artifact digest and a published source-provenance reference. It will remain pending until that evidence is available.</p>
								{/if}
							</div>
						{/if}
					</div>
				</section>

				<div class="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-[#343a44] pt-5">
					<p class="text-xs text-[#a7b1c0]">A missing proof is always shown as pending.</p>
					{#if model}
						<div class="flex gap-2"><button type="button" class="verify-action" disabled={verifying} on:click={verify}>{#if verifying}<Spinner className="size-3.5" />{/if}{verifying ? 'Checking…' : 'Verify live runtime'}</button><button type="button" class="verify-secondary" on:click={() => window.dispatchEvent(new Event('adverserial:clear-confidential-transcript'))}>Delete local transcript</button><a href={verificationConfig?.verificationUrl ?? 'https://verify.adverserial.ai'} target="_blank" rel="noopener noreferrer" class="verify-secondary">Details</a></div>
					{:else}
						<a href="https://verify.adverserial.ai" target="_blank" rel="noopener noreferrer" class="verify-secondary">Open verification site</a>
					{/if}
				</div>
			</div>
		</aside>
	</div>
{/if}

<style>
	.verification-center-drawer { border-radius: 0; }
	.verification-modal { background-image: linear-gradient(rgb(255 255 255 / 0.012) 1px, transparent 1px), linear-gradient(90deg, rgb(255 255 255 / 0.012) 1px, transparent 1px); background-size: 18px 18px; }
	.summary-card { border: 1px solid #3a424e; border-radius: 0.75rem; background: rgb(40 46 56 / 0.72); padding: 1rem; }
	.verification-module { overflow: hidden; border: 1px solid #343a44; border-radius: 0.75rem; background: #282e38; }
	.module-header { display: flex; width: 100%; align-items: center; gap: 0.75rem; padding: 0.9rem; color: inherit; text-align: left; }
	.module-header:hover { background: rgb(255 255 255 / 0.025); }
	.module-icon { display: flex; width: 2rem; height: 2rem; flex: 0 0 auto; align-items: center; justify-content: center; border: 1px solid rgb(145 181 164 / 0.3); border-radius: 0.5rem; background: rgb(145 181 164 / 0.07); color: #a1c4b3; }
	.module-header strong { display: block; color: #edf0f5; font-size: 0.84rem; font-weight: 600; }
	.module-header small { display: block; margin-top: 0.2rem; color: #a7b1c0; font-size: 0.68rem; line-height: 1rem; }
	.module-state { flex: 0 0 auto; border: 1px solid #626870; border-radius: 999px; padding: 0.25rem 0.45rem; color: #a7b1c0; font-size: 0.6rem; font-weight: 600; letter-spacing: 0.04em; }
	.verified-state { border-color: #668775; background: rgb(145 181 164 / 0.09); color: #b9d5c8; }
	.failed-state { border-color: #6e4e4e; background: rgb(221 136 136 / 0.08); color: #f0c4c4; }
	.module-chevron { color: #a7b1c0; font-size: 1rem; }
	.module-detail { border-top: 1px solid #343a44; padding: 0.95rem; background: #202224; }
	.module-detail p { margin: 0; color: #cbd2dd; font-size: 0.79rem; line-height: 1.35rem; }
	.detail-note { margin-top: 0.8rem !important; color: #a7b1c0 !important; }
	.fingerprint { position: relative; margin-top: 0.9rem; overflow: hidden; border: 1px solid #3a424e; border-radius: 0.6rem; background: #1b1d1f; padding: 0.75rem; }
	.fingerprint span { display: block; color: #a7b1c0; font-size: 0.67rem; }
	.fingerprint strong { display: block; margin-top: 0.35rem; overflow-wrap: anywhere; color: #edf0f5; font-size: 0.7rem; font-weight: 500; line-height: 1.1rem; }
	.fingerprint em { position: absolute; top: 0.65rem; right: 0.65rem; color: #b9d5c8; font-size: 0.62rem; font-style: normal; font-weight: 600; }
	.evidence-list { margin: 0.9rem 0 0; border-top: 1px solid #343a44; padding-top: 0.3rem; }
	.evidence-list div { display: grid; grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.4fr); gap: 0.75rem; border-bottom: 1px solid rgb(52 58 68 / 0.7); padding: 0.6rem 0; }
	.evidence-list dt { color: #a7b1c0; font-size: 0.68rem; }
	.evidence-list dd { margin: 0; overflow-wrap: anywhere; color: #e5ebf2; font-size: 0.68rem; text-align: right; }
	.verify-action, .verify-secondary { display: inline-flex; min-height: 2.25rem; align-items: center; justify-content: center; gap: 0.4rem; border-radius: 0.5rem; padding: 0.5rem 0.85rem; font-size: 0.78rem; font-weight: 600; transition: background-color 150ms ease, border-color 150ms ease; }
	.verify-action { border: 1px solid #668775; background: #475f53; color: #e5ebf2; }
	.verify-action:hover { background: #496d5c; }
	.verify-action:disabled { cursor: not-allowed; opacity: 0.6; }
	.verify-secondary { border: 1px solid #3a424e; color: #edf0f5; }
	.verify-secondary:hover { border-color: #626870; background: rgb(255 255 255 / 0.05); }
	@media (max-width: 520px) { .module-header { gap: 0.55rem; padding: 0.75rem; } .module-state { display: none; } .evidence-list div { grid-template-columns: 1fr; gap: 0.25rem; } .evidence-list dd { text-align: left; } }
</style>
