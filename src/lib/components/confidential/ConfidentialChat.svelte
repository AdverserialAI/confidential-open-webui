<script lang="ts">
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { models, user } from '$lib/stores';
	import {
		confidentialRuntime,
		isConfidentialModel,
		sendConfidentialCompletion,
		verifyConfidentialRuntime
	} from '$lib/confidential/client';
	import {
		deleteLocalConfidentialConversation,
		loadLocalConfidentialConversation,
		saveLocalConfidentialConversation,
		type LocalConfidentialHistory
	} from '$lib/confidential/local-history';

	type Message = {
		id: string;
		role: 'user' | 'assistant';
		content: string;
		timestamp: number;
		done: boolean;
		confidential: true;
	};

	let selectedModel = '';
	let draft = '';
	let messages: Message[] = [];
	let conversationId = '';
	let verifiedSession: Awaited<ReturnType<typeof verifyConfidentialRuntime>> | null = null;
	let working = false;
	let restored = false;
	let release: { repository?: string; tag?: string; commit?: string; status?: string } | null = null;

	$: confidentialModels = $models.filter(isConfidentialModel);
	$: if (!selectedModel && confidentialModels.length > 0) selectedModel = confidentialModels[0].id;
	$: if (selectedModel && !confidentialModels.some((model) => model.id === selectedModel)) {
		selectedModel = confidentialModels[0]?.id ?? '';
		verifiedSession = null;
	}
	$: if ($user?.id && conversationId && !restored) void restore();

	const newId = () =>
		typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
			? crypto.randomUUID()
			: `${Date.now()}-${Math.random().toString(36).slice(2)}`;

	const history = (): LocalConfidentialHistory => {
		const graph: Record<string, any> = {};
		for (let index = 0; index < messages.length; index += 1) {
			const message = messages[index];
			const next = messages[index + 1];
			graph[message.id] = {
				id: message.id,
				parentId: index > 0 ? messages[index - 1].id : null,
				childrenIds: next ? [next.id] : [],
				role: message.role,
				content: message.content,
				timestamp: message.timestamp,
				done: message.done,
				info: { confidential: true }
			};
		}
		return { messages: graph, currentId: messages.at(-1)?.id ?? null };
	};

	const persist = async () => {
		if (!$user?.id || !conversationId || !selectedModel) return;
		await saveLocalConfidentialConversation({
			ownerId: $user.id,
			conversationId,
			modelId: selectedModel,
			history: history()
		});
	};

	const restore = async () => {
		restored = true;
		try {
			const saved = await loadLocalConfidentialConversation($user.id, conversationId);
			if (!saved) return;
			selectedModel = saved.modelId;
			messages = Object.values(saved.history.messages)
				.sort((a: any, b: any) => Number(a.timestamp) - Number(b.timestamp))
				.filter((message: any) => message?.role === 'user' || message?.role === 'assistant')
				.map((message: any) => ({
					id: message.id,
					role: message.role,
					content: message.content,
					timestamp: message.timestamp,
					done: message.done === true,
					confidential: true
				}));
		} catch (error) {
			toast.error('The local browser conversation could not be restored.');
		}
	};

	onMount(() => {
		void fetch('/release.json', { cache: 'no-store' })
			.then((response) => (response.ok ? response.json() : null))
			.then((manifest) => { if (manifest?.status === 'released') release = manifest; })
			.catch(() => undefined);
		const url = new URL(window.location.href);
		const existing = url.searchParams.get('local_confidential');
		conversationId = existing && /^[a-z0-9-]{16,}$/i.test(existing) ? existing : newId();
		if (!existing) {
			url.searchParams.set('local_confidential', conversationId);
			window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
		}
	});

	const verify = async () => {
		if (!selectedModel) return toast.error('No confidential model is available to this account.');
		try {
			verifiedSession = await verifyConfidentialRuntime(selectedModel, localStorage.token);
			toast.success('Runtime evidence and the attested key were verified locally.');
		} catch (error) {
			verifiedSession = null;
			toast.error(error instanceof Error ? error.message : 'Runtime verification failed.');
		}
	};

	const send = async () => {
		const content = draft.trim();
		if (!content || working) return;
		if (!verifiedSession || verifiedSession.modelId !== selectedModel) {
			toast.error('Verify the confidential runtime before sending a prompt.');
			return;
		}
		working = true;
		const userMessage: Message = { id: newId(), role: 'user', content, timestamp: Date.now() / 1000, done: true, confidential: true };
		const answer: Message = { id: newId(), role: 'assistant', content: '', timestamp: Date.now() / 1000, done: false, confidential: true };
		messages = [...messages, userMessage, answer];
		draft = '';
		try {
			await persist();
			const { completion } = await sendConfidentialCompletion(verifiedSession, localStorage.token, {
				model: selectedModel,
				messages: messages.filter((message) => message.id !== answer.id).map(({ role, content }) => ({ role, content }))
			});
			const choice = Array.isArray(completion.choices) ? completion.choices[0] : null;
			const response = choice?.message?.content;
			if (typeof response !== 'string') throw new Error('The confidential runtime returned no assistant message.');
			answer.content = response;
			answer.done = true;
			messages = [...messages.slice(0, -1), answer];
			await persist();
		} catch (error) {
			answer.content = error instanceof Error ? error.message : 'Confidential inference failed.';
			answer.done = true;
			messages = [...messages.slice(0, -1), answer];
			await persist().catch(() => undefined);
			toast.error(answer.content);
		} finally {
			working = false;
		}
	};

	const clearLocalConversation = async () => {
		if (!$user?.id) return;
		await deleteLocalConfidentialConversation($user.id, conversationId);
		messages = [];
		conversationId = newId();
		verifiedSession = null;
		const url = new URL(window.location.href);
		url.searchParams.set('local_confidential', conversationId);
		window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
		toast.success('The local IndexedDB conversation was deleted.');
	};

	const onModelChange = () => {
		verifiedSession = null;
	};
</script>

<svelte:head>
	<title>Confidential Open WebUI</title>
</svelte:head>

<div class="shell">
	<header>
		<div>
			<p class="eyebrow">ADVERSERIAL AI · CONFIDENTIAL OPEN WEBUI</p>
			<h1>Verified private inference.</h1>
		</div>
		<a class="upstream" href="https://github.com/open-webui/open-webui" rel="noreferrer" target="_blank">Built on Open WebUI</a>
	</header>

	<section class="storage-notice" aria-label="Local conversation storage">
		<strong>Browser-local conversations</strong>
		<p>Conversation text is stored only in this browser’s IndexedDB under this site’s origin. It never enters the Open WebUI chat database, file store, tools, retrieval, or prompt APIs.</p>
	</section>

	{#if release}
		<section class="release" aria-label="Pinned source release">
			<strong>Pinned source release</strong>
			<a href={`${release.repository}/releases/tag/${release.tag}`} rel="noreferrer" target="_blank">{release.tag} · {release.commit?.slice(0, 12)}</a>
			<span>This build's source release and GitHub provenance are independently inspectable.</span>
		</section>
	{/if}

	<section class="trust">
		<div>
			<p class="eyebrow">CONFIDENTIAL INFERENCE</p>
			<h2>Verify before you send.</h2>
			<p>The browser verifies the signed policy, TEE and GPU evidence, and attested EHBP key before it encrypts a prompt. The attested API receives ciphertext and a one-use entitlement directly; Open WebUI never receives this page’s API credential, prompt, or completion.</p>
		</div>
		<div class:verified={$confidentialRuntime.status === 'verified'} class="status">
			{$confidentialRuntime.status === 'verified' ? 'Runtime verified locally' : $confidentialRuntime.status === 'verifying' ? 'Verifying evidence…' : 'Verification required'}
		</div>
	</section>

	<section class="conversation" aria-live="polite">
		{#if messages.length === 0}
			<p class="empty">This confidential conversation begins in this browser. It has no server-side transcript.</p>
		{:else}
			{#each messages as message (message.id)}
				<article class:assistant={message.role === 'assistant'} class="message">
					<span>{message.role === 'assistant' ? 'Cyber model' : 'You'}</span>
					<p>{message.content || 'Thinking securely…'}</p>
				</article>
			{/each}
		{/if}
	</section>

	<section class="composer">
		<label>
			Model
			<select bind:value={selectedModel} on:change={onModelChange} disabled={working}>
				{#each confidentialModels as model}
					<option value={model.id}>{model.name ?? model.id}</option>
				{/each}
			</select>
		</label>
		<textarea bind:value={draft} placeholder="Write a message…" rows="5" disabled={working} on:keydown={(event) => { if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') void send(); }}></textarea>
		<div class="actions">
			<button class="secondary" on:click={verify} disabled={working || !selectedModel}>Verify runtime</button>
			<button class="primary" on:click={send} disabled={working || !draft.trim() || !verifiedSession}>Send securely</button>
			<button class="text" on:click={clearLocalConversation} disabled={working}>Delete local conversation</button>
		</div>
		<p class="hint">Changing the model requires a fresh browser verification. Nothing is sent until verification succeeds.</p>
	</section>
</div>

<style>
	.shell { max-width: 980px; margin: 0 auto; padding: 40px 24px 64px; }
	header { display:flex; justify-content:space-between; gap:24px; align-items:flex-start; border-bottom:1px solid rgb(55 65 81); padding-bottom:24px; }
	h1,h2,p { margin:0; } h1 { font-size:clamp(2rem, 5vw, 3.5rem); line-height:1; margin-top:10px; letter-spacing:-.05em; } h2 { font-size:1.65rem; margin:8px 0 12px; }
	.eyebrow { color:#67e8f9; font-size:.72rem; font-weight:700; letter-spacing:.13em; } .upstream { color:#cbd5e1; font-size:.86rem; white-space:nowrap; }
	.storage-notice,.release,.trust,.conversation,.composer { border:1px solid rgb(55 65 81); border-radius:16px; margin-top:22px; padding:22px; background:rgba(17,24,39,.58); }
	.storage-notice { border-color:#0f766e; } .release { display:flex; flex-wrap:wrap; gap:8px 12px; align-items:center; font-size:.84rem; color:#cbd5e1; } .release strong { color:#f8fafc; } .release a { color:#67e8f9; text-decoration:underline; } .storage-notice strong { color:#5eead4; display:block; margin-bottom:7px; } .storage-notice p,.trust p,.hint { color:#cbd5e1; line-height:1.55; }
	.trust { display:flex; justify-content:space-between; gap:32px; } .status { height:max-content; border:1px solid #64748b; border-radius:999px; padding:8px 11px; white-space:nowrap; font-size:.84rem; color:#cbd5e1; } .status.verified { border-color:#14b8a6; color:#5eead4; }
	.conversation { min-height:240px; display:flex; flex-direction:column; gap:14px; } .empty { color:#94a3b8; margin:auto; text-align:center; max-width:470px; } .message { max-width:80%; background:#1f2937; padding:14px; border-radius:12px; align-self:flex-end; white-space:pre-wrap; } .message.assistant { align-self:flex-start; background:#0f172a; border:1px solid #334155; } .message span { color:#67e8f9; font-size:.75rem; font-weight:700; display:block; margin-bottom:6px; }
	.composer { display:flex; flex-direction:column; gap:12px; } label { color:#cbd5e1; display:grid; gap:6px; font-size:.85rem; } select,textarea { background:#111827; color:#f8fafc; border:1px solid #475569; border-radius:9px; padding:12px; font:inherit; } textarea { resize:vertical; } .actions { display:flex; align-items:center; gap:10px; flex-wrap:wrap; } button { border-radius:8px; padding:10px 14px; font-weight:700; cursor:pointer; } button:disabled { opacity:.5; cursor:not-allowed; } .primary { background:#e2e8f0; color:#0f172a; } .secondary { background:transparent; color:#5eead4; border:1px solid #14b8a6; } .text { margin-left:auto; background:transparent; color:#cbd5e1; border:0; text-decoration:underline; font-weight:500; } .hint { font-size:.8rem; }
	@media (max-width: 640px) { .shell { padding:24px 14px 48px; } header,.trust { flex-direction:column; gap:14px; } .text { margin-left:0; } .message { max-width:94%; } }
</style>
