<script lang="ts">
	import LockClosed from '$lib/components/icons/LockClosed.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import DocumentCheck from '$lib/components/icons/DocumentCheck.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import {
		confidentialVerificationConfig,
		verifyConfidentialEndpoint,
		type VerificationResult
	} from '$lib/confidential/verification';

	export let model: { id?: string; name?: string; info?: { meta?: Record<string, unknown> } } | null = null;

	let result: VerificationResult | null = null;
	let verifying = false;
	let previousModelId = '';

	$: verificationConfig = confidentialVerificationConfig(model);
	$: if (model?.id !== previousModelId) {
		previousModelId = model?.id ?? '';
		result = null;
		verifying = false;
	}

	const verify = async () => {
		if (!verificationConfig || verifying) return;
		verifying = true;
		result = await verifyConfidentialEndpoint(verificationConfig);
		verifying = false;
	};
</script>

{#if verificationConfig}
	<section class="px-3 pb-5 pt-3 text-sm" aria-live="polite" aria-label="Confidential inference proof">
		<div class="proof-console overflow-hidden rounded-xl border border-[#3a424e] bg-[#202224] text-[#edf0f5]">
			<div class="relative overflow-hidden border-b border-[#343a44] px-4 py-4">
				<div class="proof-console__glow" aria-hidden="true"></div>
				<div class="relative flex items-start gap-3">
					<div class="flex size-9 shrink-0 items-center justify-center rounded-lg border border-[#91b5a4]/30 bg-[#91b5a4]/[0.07] text-[#b9d5c8]">
						{#if result?.status === 'verified'}
							<CheckCircle className="size-4.5" strokeWidth="1.75" />
						{:else}
							<LockClosed className="size-4" strokeWidth="1.75" />
						{/if}
					</div>
					<div class="min-w-0 flex-1">
						<p class="text-[0.6rem] font-semibold tracking-[0.18em] text-[#b9d5c8]">INFERENCE RECEIPT</p>
						<h2 class="mt-1 truncate text-sm font-semibold text-white">{model?.name ?? verificationConfig.expected.modelId}</h2>
					</div>
					<span class="proof-status {result?.status === 'verified' ? 'proof-status--verified' : result?.status === 'failed' ? 'proof-status--failed' : ''}">
						{result?.status === 'verified' ? 'ATTESTED' : result?.status === 'failed' ? 'FAILED' : 'UNVERIFIED'}
					</span>
				</div>
			</div>

			<div class="proof-console__grid p-4">
				{#if result?.status === 'verified'}
					<p class="text-sm leading-5 text-[#e5ebf2]">
						The browser verified the signed receipt and its nonce, model, endpoint, policy, and evidence bindings.
					</p>
				{:else if result?.status === 'failed'}
					<p class="text-sm leading-5 text-[#f0c4c4]">Verification failed. {result.reason}</p>
				{:else}
					<p class="text-sm leading-5 text-[#c1c5c8]">Run a fresh browser-side check to request evidence and a signed runtime receipt. No trust claim is made until it validates.</p>
				{/if}

				<div class="mt-4 grid grid-cols-3 gap-2" aria-label="Receipt validation path">
					<div class="proof-step"><span>01</span><strong>Nonce</strong></div>
					<div class="proof-step"><span>02</span><strong>Receipt</strong></div>
					<div class="proof-step"><span>03</span><strong>Policy</strong></div>
				</div>

				<div class="mt-4 flex flex-wrap items-center gap-2">
					<button
						type="button"
						class="proof-verify inline-flex min-h-9 items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-60"
						disabled={verifying}
						on:click={verify}
					>
						{#if verifying}<Spinner className="size-3.5" />{:else}<DocumentCheck className="size-3.5" strokeWidth="1.75" />{/if}
						{verifying ? 'Checking receipt…' : 'Verify live runtime'}
					</button>
					<a href={verificationConfig.verificationUrl} target="_blank" rel="noopener noreferrer" class="inline-flex min-h-9 items-center rounded-lg border border-[#3a424e] px-3 py-2 text-xs font-semibold text-[#edf0f5] transition hover:bg-white/[0.05]">View details</a>
				</div>

				{#if result?.status === 'verified'}
					<dl class="mt-4 space-y-2 border-t border-[#343a44] pt-3 text-xs">
						<div class="receipt-row"><dt>Receipt issued</dt><dd>{result.proof.issuedAt}</dd></div>
						<div class="receipt-row"><dt>Evidence digest</dt><dd class="max-w-44 break-all text-[0.625rem]">{result.proof.evidenceDigest}</dd></div>
						{#if result.proof.modelDigest}<div class="receipt-row"><dt>Model artifact</dt><dd class="max-w-44 break-all text-[0.625rem]">{result.proof.modelDigest}</dd></div>{/if}
					</dl>
				{/if}

				<p class="mt-4 text-xs leading-5 text-[#a7b1c0]">The check sends a one-time nonce only. It never sends this chat’s prompts, responses, API key, cookies, or account identifier.</p>
			</div>
		</div>
	</section>
{/if}

<style>
	.proof-console { box-shadow: inset 0 1px rgb(255 255 255 / 0.04), 0 14px 34px rgb(0 0 0 / 0.16); }
	.proof-console__glow { position: absolute; inset: -50px -70px auto auto; width: 180px; height: 150px; background: radial-gradient(circle, rgb(91 210 188 / 0.13), transparent 67%); }
	.proof-console__grid { background-image: linear-gradient(rgb(255 255 255 / 0.015) 1px, transparent 1px), linear-gradient(90deg, rgb(255 255 255 / 0.015) 1px, transparent 1px); background-size: 14px 14px; }
	.proof-status { border: 1px solid rgb(174 178 183 / 0.28); border-radius: 999px; padding: 0.24rem 0.42rem; color: rgb(174 178 183); font-size: 0.53rem; font-weight: 700; letter-spacing: 0.11em; }
	.proof-status--verified { border-color: rgb(91 210 188 / 0.35); background: rgb(91 210 188 / 0.1); color: rgb(197 238 230); }
	.proof-status--failed { border-color: rgb(221 136 136 / 0.35); background: rgb(221 136 136 / 0.1); color: rgb(240 196 196); }
	.proof-step { display: flex; min-width: 0; flex-direction: column; gap: 0.2rem; border: 1px solid rgb(91 210 188 / 0.16); border-radius: 0.55rem; background: rgb(20 33 31 / 0.55); padding: 0.55rem; }
	.proof-step span { color: rgb(120 216 200); font-size: 0.56rem; }
	.proof-step strong { overflow: hidden; color: rgb(225 238 236); font-size: 0.65rem; text-overflow: ellipsis; white-space: nowrap; }
	.proof-verify { background: linear-gradient(135deg, rgb(195 232 225), rgb(91 210 188)); color: rgb(19 38 34); box-shadow: 0 8px 20px rgb(91 210 188 / 0.14); }
	.proof-verify:hover { filter: brightness(1.06); }
	.receipt-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 0.75rem; color: rgb(196 201 204); }
	.receipt-row dt { color: rgb(158 162 166); }
	.receipt-row dd { margin: 0; text-align: right; color: rgb(229 232 234); }
</style>
