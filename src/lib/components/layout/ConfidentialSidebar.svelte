<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { user, temporaryChatEnabled, models } from '$lib/stores';
	import { userSignOut } from '$lib/apis/auths';
	import {
		deleteLocalConfidentialConversation,
		listLocalConfidentialConversations,
		type LocalConfidentialConversation
	} from '$lib/confidential/local-history';
	import PencilSquare from '$lib/components/icons/PencilSquare.svelte';
	import MenuLines from '$lib/components/icons/MenuLines.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Trash from '$lib/components/icons/Trash.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import Note from '$lib/components/icons/Note.svelte';
	import Calendar from '$lib/components/icons/Calendar.svelte';
	import Cog6 from '$lib/components/icons/Cog6.svelte';
	import SignOut from '$lib/components/icons/SignOut.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';

	let conversations: LocalConfidentialConversation[] = [];
	let accountOpen = false;
	let mobileOpen = false;
	let search = '';
	let confirmDelete: string | null = null;
	let loadedFor = '';
	type MembershipStatus = {
		member: boolean;
		plan?: string;
		display_name?: string;
		credit_day_used?: number;
		credit_day_cap?: number;
		credit_week_used?: number;
		credit_week_cap?: number;
		output_day_used?: number;
		output_day_cap?: number;
		output_week_used?: number;
		output_week_cap?: number;
		daily_reset_at?: string;
		weekly_reset_at?: string;
		overage_enabled?: boolean;
	};
	let membership: MembershipStatus | null = null;
	let membershipLoading = false;
	let membershipLoadedAt = 0;
	let reloadTimer: ReturnType<typeof setTimeout> | undefined;

	$: matchingConversations = conversations.filter((conversation) =>
		titleFor(conversation).toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())
	);
	$: availableModels = ($models ?? []).filter(
		(model: any) =>
			model?.id &&
			(model?.info?.meta?.confidential_transport === true || model?.id.startsWith('lordx64/'))
	);

	const titleFor = (conversation: LocalConfidentialConversation) => {
		const firstUser = Object.values(conversation.history.messages ?? {}).find(
			(message: any) =>
				message?.role === 'user' && typeof message.content === 'string' && message.content.trim()
		) as any;
		return (
			firstUser?.content?.trim().replace(/\s+/g, ' ').slice(0, 56) || 'Confidential conversation'
		);
	};

	const reload = async () => {
		if (!$user?.id) {
			conversations = [];
			membership = null;
			return;
		}
		try {
			conversations = await listLocalConfidentialConversations($user.id);
		} catch {
			conversations = [];
		}
	};

	const loadMembership = async (force = false) => {
		if (!force && membershipLoadedAt > 0 && Date.now() - membershipLoadedAt < 30_000) return;
		const token = localStorage.getItem('token');
		if (!$user?.id || !token) {
			membership = null;
			return;
		}
		membershipLoading = true;
		try {
			const response = await fetch('/api/v1/confidential/account', {
				credentials: 'include',
				cache: 'no-store',
				headers: { authorization: `Bearer ${token}`, accept: 'application/json' }
			});
			membership = response.ok ? ((await response.json()) as MembershipStatus) : null;
		} catch {
			membership = null;
		} finally {
			membershipLoadedAt = Date.now();
			membershipLoading = false;
		}
	};

	const usagePercent = (used?: number, cap?: number) =>
		used !== undefined && cap && cap > 0 ? Math.min(100, Math.round((used / cap) * 100)) : 0;
	const credit = (value?: number) => `${Math.max(0, value ?? 0).toFixed(2)} credits`;
	const tokens = (value?: number) =>
		new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(
			Math.max(0, value ?? 0)
		);
	const toggleAccount = () => {
		accountOpen = !accountOpen;
		if (accountOpen) void loadMembership();
	};

	const newConversation = () => {
		accountOpen = false;
		mobileOpen = false;
		temporaryChatEnabled.set(false);
		window.location.assign('/');
	};

	const openConversation = (conversationId: string) => {
		accountOpen = false;
		mobileOpen = false;
		temporaryChatEnabled.set(false);
		window.location.assign(`/?local_confidential=${encodeURIComponent(conversationId)}`);
	};

	const deleteConversation = async (conversation: LocalConfidentialConversation) => {
		if (!$user?.id) return;
		try {
			await deleteLocalConfidentialConversation($user.id, conversation.conversationId);
			conversations = conversations.filter((item) => item.key !== conversation.key);
			confirmDelete = null;
			window.dispatchEvent(new Event('adverserial:local-confidential-history-changed'));
			const activeConversation = new URLSearchParams(window.location.search).get(
				'local_confidential'
			);
			if (activeConversation === conversation.conversationId) newConversation();
		} catch {
			// Preserve the record in the list when IndexedDB rejects the deletion.
			confirmDelete = null;
		}
	};

	const signOut = async () => {
		await userSignOut().catch(() => undefined);
		localStorage.removeItem('token');
		user.set(undefined);
		await goto('/auth?redirect=%2F');
	};

	const handleChange = () => {
		if (reloadTimer) clearTimeout(reloadTimer);
		reloadTimer = setTimeout(() => void reload(), 100);
	};
	onMount(() => {
		void reload();
		void loadMembership();
		window.addEventListener('adverserial:local-confidential-history-changed', handleChange);
		return () => {
			window.removeEventListener('adverserial:local-confidential-history-changed', handleChange);
			if (reloadTimer) clearTimeout(reloadTimer);
		};
	});
	$: if ($user?.id && loadedFor !== $user.id) {
		loadedFor = $user.id;
		membershipLoadedAt = 0;
		void reload();
		void loadMembership(true);
	}
</script>

<button
	class="mobile-nav"
	on:click={() => (mobileOpen = true)}
	aria-label="Open local chat history"
>
	<MenuLines className="size-5" />
	<span>Menu</span>
</button>
{#if mobileOpen}
	<button
		class="sidebar-scrim"
		aria-label="Close local chat history"
		on:click={() => (mobileOpen = false)}
	></button>
{/if}

<aside class:open={mobileOpen} class="confidential-sidebar" aria-label="Confidential conversations">
	<header class="sidebar-head">
		<div class="eyebrow">Adverserial AI / confidential</div>
		<button
			class="close-mobile"
			on:click={() => (mobileOpen = false)}
			aria-label="Close local chat history"><XMark className="size-5" /></button
		>
		<div class="brand"><span class="brand-mark">A</span><span>CyberGLM</span></div>
		<p>Private intelligence, verified before inference.</p>
	</header>

	<button class="new-chat" on:click={newConversation}
		><PencilSquare className="size-5" /> <span>New chat</span><kbd>⌘ K</kbd></button
	>
	<label class="search-box"
		><Search className="size-4" /><input
			bind:value={search}
			placeholder="Search this browser"
			aria-label="Search local conversations"
		/></label
	>

	<a class="side-action" href="/notes"
		><Note className="size-4" /> <span>Notes</span><span>↗</span></a
	>

	<section class="model-list" aria-label="Models">
		<div class="section-title"><span>01 / Models</span><span>confidential</span></div>
		{#each availableModels as model (model.id)}
			{@const comingSoon = model.id === 'lordx64/cyberkimi'}
			<Tooltip
				content={comingSoon ? 'Coming soon — CyberKIMI is not available yet.' : ''}
				className="block"
			>
				<div
					class:comingSoon
					class="model-row"
					aria-label={comingSoon ? 'CyberKIMI — coming soon' : undefined}
				>
					<span class="model-mark">A</span><span
						>{model.name ?? (model.id === 'lordx64/cyberglm' ? 'CyberGLM' : model.id)}</span
					>
					{#if comingSoon}<small>Coming soon</small>{/if}
				</div>
			</Tooltip>
		{/each}
	</section>

	<section class="history" aria-label="Local conversation history">
		<div class="history-title">
			<span>02 / Conversations</span><Tooltip
				content="This session is stored within your browser. It is never saved to our servers."
				className="flex"><span class="local-only">Browser only</span></Tooltip
			>
		</div>
		{#if matchingConversations.length === 0}
			<p class="empty">
				{search
					? 'No local conversations match.'
					: 'Saved conversations live only in this browser. Temporary chats are never stored.'}
			</p>
		{:else}
			{#each matchingConversations as conversation (conversation.key)}
				<div class:confirming={confirmDelete === conversation.key} class="conversation-row">
					{#if confirmDelete === conversation.key}
						<div class="delete-confirm">
							<span>Delete from this browser?</span><button
								on:click={() => deleteConversation(conversation)}>Delete</button
							><button on:click={() => (confirmDelete = null)}>Keep</button>
						</div>
					{:else}
						<button
							class="conversation"
							on:click={() => openConversation(conversation.conversationId)}
							title={titleFor(conversation)}>{titleFor(conversation)}</button
						>
						<button
							class="delete-conversation"
							on:click={() => (confirmDelete = conversation.key)}
							aria-label={`Delete ${titleFor(conversation)} from this browser`}
							title="Delete from this browser"><Trash className="size-4" /></button
						>
					{/if}
				</div>
			{/each}
		{/if}
	</section>

	<div class="sidebar-footer">
		<a class="privacy-note" href="/confidential"
			><span>Local-only history</span><strong>How this chat stays private ↗</strong></a
		>
		{#if accountOpen}
			<div class="account-menu">
				<div class="account-heading">
					<span class="avatar"
						>{($user?.name || $user?.email || 'A').slice(0, 1).toLocaleLowerCase()}</span
					><span><small>Account</small><strong>{$user?.name || 'Account'}</strong></span><button
						on:click={() => (accountOpen = false)}
						aria-label="Close account menu">×</button
					>
				</div>
				{#if membershipLoading}
					<p class="usage-state">Loading membership status…</p>
				{:else if membership?.member}
					<section class="usage-card" aria-label="Membership usage">
						<div class="usage-heading">
							<span>{membership.display_name}</span><span
								>{membership.overage_enabled ? 'Paid overages: on' : 'Included usage'}</span
							>
						</div>
						<div class="remaining">
							<strong
								>{credit(
									(membership.credit_week_cap ?? 0) - (membership.credit_week_used ?? 0)
								)}</strong
							><span>weekly credit remaining</span>
						</div>
						<div class="usage-row">
							<div>
								<span>Credits today</span><b
									>{credit(membership.credit_day_used)} / {credit(membership.credit_day_cap)}</b
								>
							</div>
							<i
								><em
									style={`width:${usagePercent(membership.credit_day_used, membership.credit_day_cap)}%`}
								></em></i
							>
						</div>
						<div class="usage-row">
							<div>
								<span>Credits this week</span><b
									>{credit(membership.credit_week_used)} / {credit(membership.credit_week_cap)}</b
								>
							</div>
							<i
								><em
									style={`width:${usagePercent(membership.credit_week_used, membership.credit_week_cap)}%`}
								></em></i
							>
						</div>
						<div class="usage-row">
							<div>
								<span>Output today</span><b
									>{tokens(membership.output_day_used)} / {tokens(membership.output_day_cap)}</b
								>
							</div>
							<i
								><em
									style={`width:${usagePercent(membership.output_day_used, membership.output_day_cap)}%`}
								></em></i
							>
						</div>
						<div class="usage-row">
							<div>
								<span>Output this week</span><b
									>{tokens(membership.output_week_used)} / {tokens(membership.output_week_cap)}</b
								>
							</div>
							<i
								><em
									style={`width:${usagePercent(membership.output_week_used, membership.output_week_cap)}%`}
								></em></i
							>
						</div>
						<div class="usage-reset">
							<span
								>Daily reset: {membership.daily_reset_at
									? new Date(membership.daily_reset_at).toLocaleString()
									: '—'}</span
							><span
								>Weekly reset: {membership.weekly_reset_at
									? new Date(membership.weekly_reset_at).toLocaleString()
									: '—'}</span
							>
						</div>
					</section>
				{:else}
					<p class="usage-state">No active membership. Usage is billed from your wallet.</p>
				{/if}
				<a class="account-action" href="/billing">Billing &amp; membership</a>
				<a class="account-action" href="/notes"><Note className="size-4" /> Notes</a>
				<a class="account-action" href="/calendar"><Calendar className="size-4" /> Calendar</a>
				<a class="account-action" href="/settings"><Cog6 className="size-4" /> Settings</a>
				<button class="account-action signout" on:click={signOut}
					><SignOut className="size-4" /> Sign out</button
				>
			</div>
		{/if}
		<button class="account" on:click={toggleAccount} aria-expanded={accountOpen}>
			<span class="avatar"
				>{($user?.name || $user?.email || 'A').slice(0, 1).toLocaleLowerCase()}</span
			>
			<span><small>Signed in</small><strong>{$user?.name || 'Your profile'}</strong></span><span
				aria-hidden="true">···</span
			>
		</button>
	</div>
</aside>

<style>
	:global(:root) {
		--ad-paper: #d8dadd;
		--ad-ink: #191b1d;
		--ad-muted: #a6adb7;
		--ad-line: rgb(216 218 221 / 0.16);
		--ad-panel: #181a1c;
		--ad-raised: #202326;
		--ad-acid: #c9e8de;
	}
	.mobile-nav {
		position: fixed;
		top: 0.8rem;
		left: 0.8rem;
		z-index: 30;
		display: flex;
		align-items: center;
		gap: 0.45rem;
		border: 1px solid #484e54;
		border-radius: 0;
		background: #191b1d;
		color: #f2f3f4;
		padding: 0.62rem 0.78rem;
		font-size: 0.68rem;
		font-family: 'JetBrains Mono', monospace;
		letter-spacing: 0.07em;
		text-transform: uppercase;
		box-shadow: 0 8px 22px rgb(0 0 0/0.24);
	}
	.sidebar-scrim {
		position: fixed;
		inset: 0;
		z-index: 39;
		border: 0;
		background: rgb(0 0 0/0.6);
	}
	.confidential-sidebar {
		position: fixed;
		inset: 0 auto 0 0;
		z-index: 40;
		display: none;
		width: min(21rem, calc(100vw - 1.6rem));
		flex-direction: column;
		border-right: 1px solid var(--ad-line);
		background: var(--ad-panel);
		color: #e9ecef;
		padding: 1rem 0.7rem 0.75rem;
		box-shadow: 16px 0 48px rgb(0 0 0/0.45);
	}
	.confidential-sidebar:before {
		content: '';
		position: absolute;
		inset: 0;
		pointer-events: none;
		opacity: 0.25;
		background-image:
			linear-gradient(rgb(255 255 255/0.045) 1px, transparent 1px),
			linear-gradient(90deg, rgb(255 255 255/0.045) 1px, transparent 1px);
		background-size: 28px 28px;
	}
	.confidential-sidebar > * {
		position: relative;
	}
	.confidential-sidebar.open {
		display: flex;
	}
	.sidebar-head {
		position: relative;
		border-bottom: 1px solid var(--ad-line);
		padding: 0.3rem 0.35rem 1rem;
	}
	.eyebrow,
	.section-title,
	.history-title,
	.account small,
	.brand + p {
		font-family: 'JetBrains Mono', ui-monospace, monospace;
		letter-spacing: 0.09em;
		text-transform: uppercase;
	}
	.eyebrow {
		font-size: 0.56rem;
		color: #b9c0c8;
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 0.7rem;
		margin-top: 0.8rem;
		font-size: 1.22rem;
		font-weight: 650;
		letter-spacing: -0.04em;
	}
	.brand-mark,
	.model-mark {
		display: grid;
		place-items: center;
		border: 1px solid rgb(216 218 221/0.28);
		background: #25282b;
		color: var(--ad-paper);
		font-family: 'JetBrains Mono', monospace;
		font-weight: 700;
	}
	.brand-mark {
		width: 2.1rem;
		height: 2.1rem;
		font-size: 0.7rem;
	}
	.sidebar-head p {
		margin: 0.62rem 0 0;
		max-width: 15rem;
		color: #9ca4ae;
		font-size: 0.72rem;
		line-height: 1.45;
	}
	.close-mobile {
		position: absolute;
		top: 0.05rem;
		right: 0.12rem;
		display: grid;
		place-items: center;
		border: 0;
		background: transparent;
		color: #d1d7de;
		padding: 0.3rem;
	}
	.new-chat {
		display: flex;
		align-items: center;
		gap: 0.7rem;
		width: 100%;
		border: 1px solid #d5d9de;
		background: var(--ad-paper);
		color: var(--ad-ink);
		padding: 0.78rem 0.85rem;
		margin-top: 0.85rem;
		font-size: 0.88rem;
		font-weight: 650;
		text-align: left;
		transition:
			background 0.16s ease,
			transform 0.16s ease;
	}
	.new-chat:hover {
		background: #fff;
		transform: translateY(-1px);
	}
	.new-chat kbd {
		margin-left: auto;
		border: 1px solid rgb(25 27 29/0.35);
		padding: 0.08rem 0.2rem;
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.54rem;
		font-weight: 500;
	}
	.search-box {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		margin: 0.8rem 0.25rem 0.55rem;
		border-bottom: 1px solid var(--ad-line);
		padding: 0.48rem 0.08rem;
		color: #aab3bd;
	}
	.search-box input {
		min-width: 0;
		width: 100%;
		border: 0;
		outline: 0;
		background: transparent;
		color: #edf0f4;
		font: inherit;
		font-size: 0.78rem;
	}
	.search-box input::placeholder {
		color: #858e99;
	}
	.side-action {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		margin: 0.05rem 0.25rem 0.45rem;
		border-bottom: 1px solid var(--ad-line);
		padding: 0.48rem 0.08rem 0.7rem;
		color: #cbd2d9;
		font-size: 0.73rem;
		text-decoration: none;
	}

	.side-action span:last-child {
		margin-left: auto;
		color: #8cd4c2;
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.68rem;
	}

	.side-action:hover {
		color: #fff;
	}

	.section-title,
	.history-title {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.75rem 0.35rem 0.42rem;
		color: #8c96a1;
		font-size: 0.55rem;
	}
	.section-title span:last-child {
		color: #6bd2ba;
	}
	.model-list {
		padding-bottom: 0.28rem;
		border-bottom: 1px solid var(--ad-line);
	}
	.model-row {
		display: flex;
		align-items: center;
		gap: 0.65rem;
		margin: 0.08rem 0;
		padding: 0.52rem 0.42rem;
		color: #e0e5ea;
		font-size: 0.84rem;
	}
	.model-row:hover {
		background: rgb(255 255 255/0.055);
	}
	.model-row.comingSoon {
		color: #a5adb5;
		cursor: help;
	}
	.model-row small {
		margin-left: auto;
		color: #77818b;
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.55rem;
		text-transform: uppercase;
	}
	.model-mark {
		width: 1.46rem;
		height: 1.46rem;
		font-size: 0.48rem;
	}
	.history {
		min-height: 0;
		flex: 1;
		overflow: auto;
		margin-top: 0.22rem;
		padding-right: 0.08rem;
	}
	.history-title .local-only {
		color: #9bd4c6;
		font-size: 0.53rem;
		cursor: help;
	}
	.empty {
		margin: 0.35rem 0.35rem;
		color: #89929c;
		font-size: 0.72rem;
		line-height: 1.5;
	}
	.conversation-row {
		display: flex;
		align-items: center;
		margin: 0.03rem 0;
		border: 1px solid transparent;
	}
	.conversation-row:hover {
		border-color: rgb(216 218 221/0.09);
		background: rgb(255 255 255/0.035);
	}
	.conversation-row.confirming {
		border-color: #7f9e95;
		background: #25312f;
	}
	.conversation {
		display: block;
		min-width: 0;
		flex: 1;
		overflow: hidden;
		border: 0;
		background: transparent;
		color: #dbe1e7;
		padding: 0.56rem 0.42rem;
		text-align: left;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.77rem;
	}
	.delete-conversation {
		display: grid;
		place-items: center;
		visibility: hidden;
		border: 0;
		background: transparent;
		color: #aab2bb;
		padding: 0.45rem;
	}
	.conversation-row:hover .delete-conversation,
	.delete-conversation:focus {
		visibility: visible;
	}
	.delete-conversation:hover {
		color: #fff;
		background: #733c3c;
	}
	.delete-confirm {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		width: 100%;
		padding: 0.38rem 0.42rem;
		color: #dce8e4;
		font-size: 0.65rem;
	}
	.delete-confirm span {
		min-width: 0;
		flex: 1;
	}
	.delete-confirm button {
		border: 1px solid #6c8780;
		background: transparent;
		color: #e6f4ef;
		padding: 0.22rem 0.32rem;
		font-size: 0.62rem;
	}
	.delete-confirm button:first-of-type {
		background: #d2e5dc;
		color: #182521;
		border-color: #d2e5dc;
	}
	.sidebar-footer {
		position: relative;
		border-top: 1px solid var(--ad-line);
		padding-top: 0.65rem;
	}
	.privacy-note {
		display: grid;
		gap: 0.14rem;
		margin: 0 0.1rem 0.65rem;
		border-left: 2px solid #92d6c5;
		padding: 0.1rem 0.5rem;
		text-decoration: none;
	}
	.privacy-note span {
		color: #94a0ab;
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.53rem;
		letter-spacing: 0.07em;
		text-transform: uppercase;
	}
	.privacy-note strong {
		color: #dce5e5;
		font-size: 0.68rem;
		font-weight: 500;
	}
	.account {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		width: 100%;
		border: 1px solid #454c54;
		background: #24272a;
		color: #e5e9ec;
		padding: 0.6rem 0.65rem;
		text-align: left;
	}
	.account > span:nth-child(2) {
		display: grid;
		min-width: 0;
		flex: 1;
		gap: 0.1rem;
	}
	.account strong {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.78rem;
	}
	.account small {
		overflow: hidden;
		color: #909aa5;
		font-size: 0.51rem;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.avatar {
		display: grid;
		place-items: center;
		width: 1.9rem;
		height: 1.9rem;
		flex: 0 0 auto;
		border-radius: 50%;
		background: #1988cb;
		color: #fff;
		font-size: 0.8rem;
		font-weight: 700;
	}
	.account-menu {
		position: absolute;
		z-index: 2;
		bottom: calc(100% + 0.45rem);
		left: 0.05rem;
		right: 0.05rem;
		display: grid;
		gap: 0.6rem;
		max-height: calc(100vh - 1rem);
		overflow: auto;
		border: 1px solid #5d666f;
		background: #24272a;
		padding: 0.82rem;
		box-shadow: 0 16px 45px rgb(0 0 0/0.55);
	}
	.account-heading {
		display: flex;
		align-items: center;
		gap: 0.6rem;
	}
	.account-heading > span:nth-child(2) {
		display: grid;
		flex: 1;
		gap: 0.06rem;
	}
	.account-heading strong {
		font-size: 0.88rem;
	}
	.account-heading small {
		color: #9ca5ae;
		font-size: 0.53rem;
	}
	.account-heading button {
		border: 0;
		background: transparent;
		color: #bec7ce;
		font-size: 1.45rem;
	}
	.usage-state {
		margin: 0;
		color: #c5ccd4;
		line-height: 1.4;
		font-size: 0.73rem;
	}
	.usage-card {
		display: grid;
		gap: 0.65rem;
		border-top: 1px solid #454b52;
		padding-top: 0.65rem;
	}
	.usage-heading {
		display: flex;
		align-items: center;
		justify-content: space-between;
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.58rem;
		letter-spacing: 0.06em;
		color: #eef1f4;
	}
	.usage-heading span:last-child {
		color: #a9b2ba;
		font-size: 0.52rem;
		letter-spacing: 0;
	}
	.remaining {
		display: grid;
		gap: 0.05rem;
	}
	.remaining strong {
		font-size: 0.96rem;
		color: #fff;
	}
	.remaining span {
		font-size: 0.66rem;
		color: #aeb7c0;
	}
	.usage-row {
		display: grid;
		gap: 0.28rem;
	}
	.usage-row > div {
		display: flex;
		justify-content: space-between;
		gap: 0.5rem;
		font-size: 0.68rem;
		color: #d4dae1;
	}
	.usage-row b {
		font-weight: 500;
		color: #e7ebef;
	}
	.usage-row i {
		display: block;
		height: 0.28rem;
		overflow: hidden;
		background: #4c535a;
	}
	.usage-row em {
		display: block;
		height: 100%;
		background: #b9c4c2;
	}
	.usage-reset {
		display: grid;
		gap: 0.2rem;
		color: #b9c0c8;
		font-size: 0.64rem;
		line-height: 1.35;
	}
	.account-action {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		border: 0;
		border-top: 1px solid #42484f;
		background: transparent;
		color: #e1e5e9;
		padding: 0.56rem 0.05rem;
		font: inherit;
		text-decoration: none;
		text-align: left;
		font-size: 0.78rem;
	}
	.signout {
		cursor: pointer;
	}
	@media (min-width: 768px) {
		.mobile-nav,
		.sidebar-scrim,
		.close-mobile {
			display: none;
		}
		.confidential-sidebar {
			display: flex;
			width: 17.5rem;
			box-shadow: none;
		}
	}
	@media (max-width: 767px) {
		.history {
			max-height: none;
		}
		.account-menu {
			position: fixed;
			left: 0.8rem;
			right: 0.8rem;
			bottom: 0.8rem;
		}
		.new-chat {
			margin-top: 0.7rem;
		}
	}
</style>
