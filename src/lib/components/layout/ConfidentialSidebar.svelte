<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { user, temporaryChatEnabled } from '$lib/stores';
	import { userSignOut } from '$lib/apis/auths';
	import {
		listLocalConfidentialConversations,
		type LocalConfidentialConversation
	} from '$lib/confidential/local-history';
	import ChatPlus from '$lib/components/icons/ChatPlus.svelte';
	import UserCircle from '$lib/components/icons/UserCircle.svelte';
	import LockClosed from '$lib/components/icons/LockClosed.svelte';
	import MenuLines from '$lib/components/icons/MenuLines.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	let conversations: LocalConfidentialConversation[] = [];
	let accountOpen = false;
	let mobileOpen = false;
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

	const titleFor = (conversation: LocalConfidentialConversation) => {
		const firstUser = Object.values(conversation.history.messages ?? {}).find(
			(message: any) => message?.role === 'user' && typeof message.content === 'string' && message.content.trim()
		) as any;
		return firstUser?.content?.trim().replace(/\s+/g, ' ').slice(0, 56) || 'Confidential conversation';
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

	const loadMembership = async () => {
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
			membershipLoading = false;
		}
	};

	const usagePercent = (used?: number, cap?: number) =>
		used !== undefined && cap && cap > 0 ? Math.min(100, Math.round((used / cap) * 100)) : 0;
	const credit = (value?: number) => `${Math.max(0, value ?? 0).toFixed(2)} credits`;
	const tokens = (value?: number) => new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(Math.max(0, value ?? 0));
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

	const signOut = async () => {
		await userSignOut().catch(() => undefined);
		localStorage.removeItem('token');
		user.set(null);
		await goto('/auth?redirect=%2F');
	};

	const handleChange = () => void reload();
	onMount(() => {
		void reload();
		void loadMembership();
		window.addEventListener('adverserial:local-confidential-history-changed', handleChange);
		return () => window.removeEventListener('adverserial:local-confidential-history-changed', handleChange);
	});
	$: if ($user?.id) {
		void reload();
		void loadMembership();
	}
</script>

<button class="mobile-nav" on:click={() => (mobileOpen = true)} aria-label="Open local chat history">
	<MenuLines className="size-5" />
	<span>Chats</span>
</button>
{#if mobileOpen}
	<button class="sidebar-scrim" aria-label="Close local chat history" on:click={() => (mobileOpen = false)}></button>
{/if}

<aside class:open={mobileOpen} class="confidential-sidebar" aria-label="Confidential conversations">
	<div class="sidebar-head">
		<button class="close-mobile" on:click={() => (mobileOpen = false)} aria-label="Close local chat history"><XMark className="size-5" /></button>
		<div class="brand"><span class="brand-mark">A</span><span>ADVERSERIAL AI</span></div>
		<p>Confidential chat</p>
	</div>

	<button class="new-chat" on:click={newConversation}><ChatPlus className="size-4" /> New confidential chat</button>
	<div class="browser-notice"><LockClosed className="size-3.5" /> Saved only in this browser</div>

	<section class="history" aria-label="Local conversation history">
		<div class="history-label">Local history</div>
		{#if conversations.length === 0}
			<p class="empty">Saved conversations appear here. Temporary chats are never stored.</p>
		{:else}
			{#each conversations as conversation (conversation.key)}
				<button class="conversation" on:click={() => openConversation(conversation.conversationId)} title={titleFor(conversation)}>{titleFor(conversation)}</button>
			{/each}
		{/if}
	</section>

	<div class="sidebar-footer">
		<a class="membership" href="/billing"><span>Membership &amp; billing</span><span aria-hidden="true">↗</span></a>
		<button class="account" on:click={toggleAccount} aria-expanded={accountOpen}>
			<UserCircle className="size-7" />
			<span><strong>{$user?.name || 'Your profile'}</strong><small>{$user?.email || 'Signed-in account'}</small></span>
			<span aria-hidden="true">···</span>
		</button>
		{#if accountOpen}
			<div class="account-menu">
				<div><strong>{$user?.name || 'Account'}</strong><small>Identity is used only for access and entitlements.</small></div>
				{#if membershipLoading}
					<p class="usage-state">Loading membership status…</p>
				{:else if membership?.member}
					<section class="usage-card" aria-label="Membership usage">
						<div class="usage-heading"><span>{membership.display_name}</span><span>{membership.overage_enabled ? 'Paid usage on' : 'Included usage'}</span></div>
						<div class="remaining"><strong>{credit((membership.credit_week_cap ?? 0) - (membership.credit_week_used ?? 0))}</strong><span>weekly credit remaining</span></div>
						<div class="usage-row"><div><span>Daily credits</span><b>{credit(membership.credit_day_used)} / {credit(membership.credit_day_cap)}</b></div><i><em style={`width:${usagePercent(membership.credit_day_used, membership.credit_day_cap)}%`}></em></i></div>
						<div class="usage-row"><div><span>Weekly credits</span><b>{credit(membership.credit_week_used)} / {credit(membership.credit_week_cap)}</b></div><i><em style={`width:${usagePercent(membership.credit_week_used, membership.credit_week_cap)}%`}></em></i></div>
						<div class="usage-row"><div><span>Output today</span><b>{tokens(membership.output_day_used)} / {tokens(membership.output_day_cap)}</b></div><i><em style={`width:${usagePercent(membership.output_day_used, membership.output_day_cap)}%`}></em></i></div>
						<div class="usage-row"><div><span>Output this week</span><b>{tokens(membership.output_week_used)} / {tokens(membership.output_week_cap)}</b></div><i><em style={`width:${usagePercent(membership.output_week_used, membership.output_week_cap)}%`}></em></i></div>
						<div class="usage-reset"><span>Daily reset {membership.daily_reset_at ? new Date(membership.daily_reset_at).toLocaleString() : '—'}</span><span>Weekly reset {membership.weekly_reset_at ? new Date(membership.weekly_reset_at).toLocaleString() : '—'}</span></div>
					</section>
				{:else}
					<p class="usage-state">No active membership. Usage is billed from your wallet.</p>
				{/if}
				<a href="/billing">Manage membership</a>
				<button on:click={signOut}>Sign out</button>
			</div>
		{/if}
	</div>
</aside>

<style>
	.mobile-nav { position:fixed; top:.75rem; left:.75rem; z-index:30; display:flex; align-items:center; gap:.4rem; border:1px solid rgb(71 85 105); border-radius:.5rem; background:rgb(17 24 39 / .94); color:rgb(229 231 235); padding:.45rem .6rem; font-size:.76rem; font-weight:600; box-shadow:0 4px 20px rgb(0 0 0 / .2); }
	.sidebar-scrim { position:fixed; inset:0; z-index:39; border:0; background:rgb(0 0 0 / .48); }
	.confidential-sidebar { position: fixed; inset: 0 auto 0 0; z-index: 40; display: none; width: min(17.5rem, calc(100vw - 2.5rem)); flex-direction: column; border-right: 1px solid rgb(55 65 81); background: rgb(17 24 39); color: rgb(229 231 235); padding: 1rem .75rem; box-shadow: 14px 0 35px rgb(0 0 0 / .32); }
	.confidential-sidebar.open { display:flex; }
	.close-mobile { position:absolute; top:.7rem; right:.7rem; display:grid; place-items:center; border:0; border-radius:.4rem; background:transparent; color:rgb(203 213 225); padding:.3rem; }
	.sidebar-head { padding: .3rem .45rem 1rem; border-bottom: 1px solid rgb(55 65 81 / .72); } .brand { display:flex; align-items:center; gap:.5rem; font-size:.76rem; font-weight:700; letter-spacing:.045em; } .brand-mark { display:grid; place-items:center; width:1.35rem; height:1.35rem; border:1px solid rgb(148 163 184); border-radius:.35rem; font-size:.7rem; } .sidebar-head p { margin:.5rem 0 0; color:rgb(148 163 184); font-size:.72rem; text-transform:uppercase; letter-spacing:.13em; }
	.new-chat { display:flex; align-items:center; justify-content:center; gap:.45rem; width:100%; margin-top:1rem; border:1px solid rgb(100 116 139); border-radius:.55rem; background:rgb(31 41 55); color:#fff; padding:.65rem .75rem; font-size:.82rem; font-weight:600; transition:background .15s; } .new-chat:hover { background:rgb(55 65 81); }
	.browser-notice { display:flex; align-items:center; gap:.4rem; margin:.8rem .25rem 0; color:rgb(94 234 212); font-size:.68rem; }
	.history { min-height:0; flex:1; overflow-y:auto; margin-top:1.25rem; padding:.1rem .15rem; } .history-label { margin:0 .3rem .55rem; color:rgb(148 163 184); font-size:.67rem; letter-spacing:.12em; text-transform:uppercase; } .empty { margin:.2rem .3rem; color:rgb(148 163 184); font-size:.75rem; line-height:1.35; } .conversation { display:block; width:100%; overflow:hidden; border:0; border-radius:.45rem; background:transparent; color:rgb(209 213 219); padding:.55rem .6rem; text-align:left; text-overflow:ellipsis; white-space:nowrap; font-size:.8rem; } .conversation:hover { background:rgb(31 41 55); color:#fff; }
	.sidebar-footer { position:relative; display:grid; gap:.5rem; border-top:1px solid rgb(55 65 81 / .72); padding-top:.8rem; } .membership,.account { display:flex; align-items:center; gap:.55rem; width:100%; border:0; border-radius:.55rem; background:transparent; color:rgb(229 231 235); padding:.55rem; font-size:.8rem; text-align:left; } .membership { justify-content:space-between; color:rgb(153 246 228); text-decoration:none; } .membership:hover,.account:hover { background:rgb(31 41 55); } .account span:nth-child(2) { display:grid; min-width:0; flex:1; gap:.1rem; } .account strong { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:.78rem; } .account small { overflow:hidden; color:rgb(148 163 184); font-size:.67rem; text-overflow:ellipsis; white-space:nowrap; }
	.account-menu { position:absolute; bottom:calc(100% + .35rem); left:0; right:0; display:grid; gap:.55rem; max-height:calc(100vh - 1.5rem); overflow-y:auto; border:1px solid rgb(71 85 105); border-radius:.65rem; background:rgb(31 41 55); padding:.75rem; box-shadow:0 15px 35px rgb(0 0 0 / .35); font-size:.76rem; } .account-menu div { display:grid; gap:.2rem; } .account-menu small { color:rgb(148 163 184); line-height:1.35; } .account-menu a,.account-menu button { border:0; border-radius:.35rem; background:rgb(55 65 81); color:#fff; padding:.45rem .55rem; font:inherit; text-decoration:none; text-align:left; } .account-menu button { background:transparent; color:rgb(252 165 165); }
	@media (min-width: 768px) { .mobile-nav,.sidebar-scrim,.close-mobile { display:none; } .confidential-sidebar { display:flex; box-shadow:none; } }
</style>
