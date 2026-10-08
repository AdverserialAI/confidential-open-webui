<script lang="ts">
	import { onMount } from 'svelte';
	import LockClosed from '$lib/components/icons/LockClosed.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import DocumentCheck from '$lib/components/icons/DocumentCheck.svelte';

	let open = false;

	onMount(() => {
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
		<button type="button" class="absolute inset-0 h-full w-full bg-black/70" on:click={() => (open = false)} aria-label="Close security explainer"></button>
		<section class="process-modal relative max-h-[min(860px,calc(100dvh-2rem))] w-full max-w-[860px] overflow-y-auto rounded-2xl border border-[#3a424e] bg-[#202224] text-[#edf0f5] shadow-2xl shadow-black/70" role="dialog" aria-modal="true" aria-labelledby="security-explainer-title">
			<header class="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-[#343a44] bg-[#202224]/95 px-6 py-5 backdrop-blur sm:px-7">
				<div class="flex items-start gap-3">
					<div class="brand-mark">A</div>
					<div>
						<p class="text-[0.625rem] font-medium tracking-[0.15em] text-[#b9d5c8]">ADVERSERIAL AI · CONFIDENTIAL INFERENCE</p>
						<h2 id="security-explainer-title" class="mt-1.5 text-xl font-semibold tracking-tight text-white">How secure is this chat?</h2>
					</div>
				</div>
				<button type="button" class="flex size-8 shrink-0 items-center justify-center rounded-md text-lg text-[#a7b1c0] transition hover:bg-white/[0.06] hover:text-white" on:click={() => (open = false)} aria-label="Close security explainer">×</button>
			</header>

			<div class="px-6 py-5 sm:px-7 sm:py-6">
				<p class="max-w-[720px] text-[0.95rem] leading-7 text-[#d6dce5]">
					Your browser verifies the confidential runtime before it encrypts a prompt. A valid proof binds the runtime, policy and encryption key; every completed inference then carries its own signed receipt.
				</p>

				<section class="process-map mt-7" aria-label="Confidential chat verification path">
					<div class="process-map__label"><CheckCircle className="size-3.5" strokeWidth="1.9" /> VERIFIED IN YOUR BROWSER</div>
					<div class="flow-grid">
						<article class="flow-card">
							<span class="flow-number">01</span>
							<h3>Browser or SDK</h3>
							<p>Loads the signed policy and asks for fresh runtime evidence.</p>
						</article>
						<span class="flow-arrow" aria-hidden="true">→</span>
						<article class="flow-card">
							<span class="flow-number">02</span>
							<h3>Independent evidence</h3>
							<p>Checks Intel TDX, NVIDIA GPU evidence, policy and key binding.</p>
						</article>
						<span class="flow-arrow" aria-hidden="true">→</span>
						<article class="flow-card flow-card--trusted">
							<span class="flow-number">03</span>
							<h3><LockClosed className="mr-1 inline size-3.5 text-[#b9d5c8]" strokeWidth="1.9" />Attested runtime</h3>
							<p>Decrypts EHBP inside the TEE and reaches inference only over local loopback.</p>
						</article>
						<span class="flow-arrow" aria-hidden="true">→</span>
						<article class="flow-card">
							<span class="flow-number">04</span>
							<h3>Signed receipt</h3>
							<p>Returns a receipt for the finished prompt and encrypted response stream.</p>
						</article>
					</div>
				</section>

				<section class="mt-7" aria-labelledby="when-verification-runs">
					<h3 id="when-verification-runs" class="section-title">When verification happens</h3>
					<div class="timing-grid">
						<div class="timing-card"><span>VERIFY RUNTIME</span><p>The <strong>Verify runtime</strong> button forces a fresh verification immediately.</p></div>
						<div class="timing-card"><span>BEFORE A PROMPT</span><p>The chat verifies again before confidential inference when no valid browser proof exists or the evidence has expired.</p></div>
						<div class="timing-card"><span>AFTER COMPLETION</span><p>It does not re-attest every output token. Each completed prompt must return its own signed inference receipt.</p></div>
					</div>
				</section>

				<section class="mt-7" aria-labelledby="compare-title">
					<div class="flex flex-wrap items-end justify-between gap-2">
						<div>
							<h3 id="compare-title" class="section-title">What you can independently compare</h3>
							<p class="mt-1 text-xs leading-5 text-[#a7b1c0]">The Verification Center exposes values the client checked, alongside public policy and release evidence.</p>
						</div>
						<a class="source-link" href="https://verify.adverserial.ai" target="_blank" rel="noopener noreferrer">Open public evidence ↗</a>
					</div>
					<div class="evidence-table-wrap mt-3">
						<table class="evidence-table">
							<thead><tr><th>Evidence</th><th>What the browser checks</th><th>Independent source</th></tr></thead>
							<tbody>
								<tr><td>Policy identity</td><td>Model ID, permitted endpoint, expected model/runtime digest and trusted receipt key.</td><td>Signed policy at <a href="https://verify.adverserial.ai" target="_blank" rel="noopener noreferrer">verify.adverserial.ai</a>.</td></tr>
								<tr><td>TDX quote</td><td>The quote, its freshness and its validation result.</td><td>Intel verification collateral and quote validation.</td></tr>
								<tr><td>GPU evidence</td><td>The GPU attestation bundle matches the configuration required by policy.</td><td>NVIDIA attestation evidence.</td></tr>
								<tr><td>TLS / HPKE key</td><td>The evidence fingerprint matches the key the browser used to encrypt the prompt.</td><td>The attestation evidence and policy binding.</td></tr>
								<tr><td>Release digests</td><td>Runtime and model digests match the published release metadata.</td><td>Public release manifest and source/build provenance.</td></tr>
								<tr><td>Prompt receipt</td><td>The exact encrypted request nonce, model, response hash, policy and attestation-state digest.</td><td>The signed receipt returned with that completed inference.</td></tr>
							</tbody>
						</table>
					</div>
				</section>

				<div class="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-[#343a44] pt-4">
					<p class="max-w-[520px] text-xs leading-5 text-[#a7b1c0]">A failed or stale proof stops this confidential client before it transmits the prompt. Open the Verification Center to inspect the current proof.</p>
					<button type="button" class="process-action" on:click={openCenter}><DocumentCheck className="mr-1.5 size-4" strokeWidth="1.8" />Open Verification Center</button>
				</div>
			</div>
		</section>
	</div>
{/if}

<style>
	.process-modal { background-image: linear-gradient(rgb(255 255 255 / 0.012) 1px, transparent 1px), linear-gradient(90deg, rgb(255 255 255 / 0.012) 1px, transparent 1px); background-size: 18px 18px; }
	.brand-mark { display: flex; width: 2.15rem; height: 2.15rem; flex: 0 0 auto; align-items: center; justify-content: center; border: 1px solid rgb(145 181 164 / 0.38); border-radius: 0.6rem; background: rgb(145 181 164 / 0.08); color: #b9d5c8; font-size: 0.8rem; font-weight: 700; }
	.process-map { position: relative; border: 1px dashed #626870; border-radius: 0.8rem; background: rgb(27 29 31 / 0.72); padding: 1.55rem 1.2rem 1.2rem; }
	.process-map__label { position: absolute; top: -1.05rem; left: 1rem; display: inline-flex; align-items: center; gap: 0.4rem; border: 1px solid #668775; border-radius: 0.35rem; background: #303640; padding: 0.35rem 0.55rem; color: #b9d5c8; font-size: 0.67rem; font-weight: 600; letter-spacing: 0.06em; }
	.flow-grid { display: grid; grid-template-columns: minmax(0,1fr) auto minmax(0,1fr) auto minmax(0,1fr) auto minmax(0,1fr); align-items: center; gap: 0.45rem; }
	.flow-card { min-height: 10rem; border: 1px solid #3a424e; border-radius: 0.6rem; background: #282e38; padding: 0.85rem; box-shadow: 0 10px 25px rgb(0 0 0 / 0.14); }
	.flow-card--trusted { border-color: #668775; background: linear-gradient(145deg, #2e3d37, #282e38 70%); }
	.flow-number { color: #a1c4b3; font-size: 0.62rem; font-weight: 600; letter-spacing: 0.08em; }
	.flow-card h3 { margin: 0.7rem 0 0; color: #f1f2f3; font-size: 0.8rem; font-weight: 600; line-height: 1.2; }
	.flow-card p { margin: 0.55rem 0 0; color: #a7b1c0; font-size: 0.72rem; line-height: 1.3rem; }
	.flow-arrow { color: #91b5a4; font-size: 1.25rem; opacity: 0.9; }
	.section-title { color: #edf0f5; font-size: 0.93rem; font-weight: 600; }
	.timing-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.55rem; margin-top: 0.75rem; }
	.timing-card { border: 1px solid #343a44; border-radius: 0.65rem; background: #282e38; padding: 0.85rem; }
	.timing-card span { color: #a1c4b3; font-size: 0.6rem; font-weight: 600; letter-spacing: 0.08em; }
	.timing-card p { margin: 0.45rem 0 0; color: #cbd2dc; font-size: 0.75rem; line-height: 1.3rem; }
	.timing-card strong { color: #edf0f5; font-weight: 600; }
	.source-link { color: #b9d5c8; font-size: 0.75rem; font-weight: 600; text-decoration: underline; text-underline-offset: 0.18rem; }
	.evidence-table-wrap { overflow-x: auto; border: 1px solid #343a44; border-radius: 0.65rem; }
	.evidence-table { width: 100%; min-width: 670px; border-collapse: collapse; text-align: left; }
	.evidence-table th { background: #282e38; color: #a1c4b3; font-size: 0.62rem; font-weight: 600; letter-spacing: 0.07em; }
	.evidence-table td { color: #cbd2dc; font-size: 0.74rem; line-height: 1.25rem; vertical-align: top; }
	.evidence-table th, .evidence-table td { border-bottom: 1px solid #343a44; padding: 0.72rem 0.75rem; }
	.evidence-table tbody tr:last-child td { border-bottom: 0; }
	.evidence-table td:first-child { width: 20%; color: #edf0f5; font-weight: 600; }
	.evidence-table td:nth-child(2) { width: 46%; }
	.evidence-table a { color: #b9d5c8; text-decoration: underline; text-underline-offset: 0.15rem; }
	.process-action { display: inline-flex; min-height: 2.3rem; align-items: center; justify-content: center; border: 1px solid #668775; border-radius: 0.5rem; background: #475f53; padding: 0.5rem 0.9rem; color: #edf0f5; font-size: 0.8rem; font-weight: 600; transition: background-color 150ms ease; }
	.process-action:hover { background: #496d5c; }
	@media (max-width: 760px) { .flow-grid { grid-template-columns: 1fr; gap: 0.6rem; } .flow-arrow { transform: rotate(90deg); justify-self: center; line-height: 1; } .flow-card { min-height: 0; } .timing-grid { grid-template-columns: 1fr; } }
</style>
