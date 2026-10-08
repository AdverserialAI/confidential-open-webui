<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { user, temporaryChatEnabled, models } from '$lib/stores';
	import { userSignOut } from '$lib/apis/auths';
	import {
		listLocalConfidentialConversations,
		type LocalConfidentialConversation
	} from '$lib/confidential/local-history';
	import PencilSquare from '$lib/components/icons/PencilSquare.svelte';
	import MenuLines from '$lib/components/icons/MenuLines.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import Note from '$lib/components/icons/Note.svelte';
	import Calendar from '$lib/components/icons/Calendar.svelte';
	import Cog6 from '$lib/components/icons/Cog6.svelte';
	import SignOut from '$lib/components/icons/SignOut.svelte';

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
	let search = '';
	$: matchingConversations = conversations.filter((conversation) =>
		titleFor(conversation).toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())
	);
	$: availableModels = ($models ?? []).filter((model: any) => model?.id && (model?.info?.meta?.confidential_transport === true || model?.id.startsWith('lordx64/')));

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
	<header class="sidebar-head">
		<button class="close-mobile" on:click={() => (mobileOpen = false)} aria-label="Close local chat history"><XMark className="size-5" /></button>
		<div class="brand"><span class="brand-mark">A</span><span>CyberGLM</span></div>
		<button class="collapse-desktop" aria-label="Collapse sidebar"><span>▣</span></button>
	</header>

	<button class="new-chat" on:click={newConversation}><PencilSquare className="size-5" /> New Chat</button>
	<label class="search-box"><Search className="size-5" /><input bind:value={search} placeholder="Search" aria-label="Search local conversations" /></label>
	<a class="side-action" href="/notes"><Note className="size-5" /> Notes</a>

	<section class="model-list" aria-label="Models">
		<div class="section-title">Models</div>
		{#each availableModels as model (model.id)}
			<div class="model-row"><span class="model-mark">A</span><span>{model.name ?? (model.id === 'lordx64/cyberglm' ? 'CyberGLM' : model.id)}</span></div>
		{/each}
	</section>

	<section class="history" aria-label="Local conversation history">
		<div class="history-title"><span>Conversations</span><span>Local only</span></div>
		{#if matchingConversations.length === 0}
			<p class="empty">{search ? 'No local conversations match.' : 'Saved conversations appear here. Temporary chats are never stored.'}</p>
		{:else}
			{#each matchingConversations as conversation (conversation.key)}
				<button class="conversation" on:click={() => openConversation(conversation.conversationId)} title={titleFor(conversation)}>{titleFor(conversation)}</button>
			{/each}
		{/if}
	</section>

	<div class="sidebar-footer">
		{#if accountOpen}
			<div class="account-menu">
				<div class="account-heading"><span class="avatar">{($user?.name || $user?.email || 'A').slice(0, 1).toLocaleLowerCase()}</span><strong>{$user?.name || 'Account'}</strong><button on:click={() => (accountOpen = false)} aria-label="Close account menu">×</button></div>
				{#if membershipLoading}
					<p class="usage-state">Loading membership status…</p>
				{:else if membership?.member}
					<section class="usage-card" aria-label="Membership usage">
						<div class="usage-heading"><span>{membership.display_name}</span><span>{membership.overage_enabled ? 'Paid overages: on' : 'Included usage'}</span></div>
						<div class="remaining"><strong>{credit((membership.credit_week_cap ?? 0) - (membership.credit_week_used ?? 0))}</strong><span>weekly credit remaining</span></div>
						<div class="usage-row"><div><span>Credits today</span><b>{credit(membership.credit_day_used)} / {credit(membership.credit_day_cap)}</b></div><i><em style={`width:${usagePercent(membership.credit_day_used, membership.credit_day_cap)}%`}></em></i></div>
						<div class="usage-row"><div><span>Credits this week</span><b>{credit(membership.credit_week_used)} / {credit(membership.credit_week_cap)}</b></div><i><em style={`width:${usagePercent(membership.credit_week_used, membership.credit_week_cap)}%`}></em></i></div>
						<div class="usage-row"><div><span>Output today</span><b>{tokens(membership.output_day_used)} / {tokens(membership.output_day_cap)}</b></div><i><em style={`width:${usagePercent(membership.output_day_used, membership.output_day_cap)}%`}></em></i></div>
						<div class="usage-row"><div><span>Output this week</span><b>{tokens(membership.output_week_used)} / {tokens(membership.output_week_cap)}</b></div><i><em style={`width:${usagePercent(membership.output_week_used, membership.output_week_cap)}%`}></em></i></div>
						<div class="usage-reset"><span>Daily reset: {membership.daily_reset_at ? new Date(membership.daily_reset_at).toLocaleString() : '—'}</span><span>Weekly reset: {membership.weekly_reset_at ? new Date(membership.weekly_reset_at).toLocaleString() : '—'}</span></div>
					</section>
				{:else}
					<p class="usage-state">No active membership. Usage is billed from your wallet.</p>
				{/if}
				<a class="account-action" href="/billing">Billing &amp; membership</a>
				<a class="account-action" href="/notes"><Note className="size-5" /> Notes</a>
				<a class="account-action" href="/calendar"><Calendar className="size-5" /> Calendar</a>
				<a class="account-action" href="/settings"><Cog6 className="size-5" /> Settings</a>
				<button class="account-action signout" on:click={signOut}><SignOut className="size-5" /> Sign Out</button>
			</div>
		{/if}
		<button class="account" on:click={toggleAccount} aria-expanded={accountOpen}>
			<span class="avatar">{($user?.name || $user?.email || 'A').slice(0, 1).toLocaleLowerCase()}</span>
			<span><strong>{$user?.name || 'Your profile'}</strong><small>{$user?.email || 'Signed-in account'}</small></span>
			<span aria-hidden="true">···</span>
		</button>
	</div>
</aside>

<style>
	.mobile-nav { position:fixed; top:.75rem; left:.75rem; z-index:30; display:flex; align-items:center; gap:.4rem; border:1px solid rgb(71 85 105); border-radius:.55rem; background:rgb(31 34 38 / .96); color:#e6eaf0; padding:.52rem .7rem; font-size:.83rem; font-weight:600; box-shadow:0 4px 20px rgb(0 0 0 / .2); }
	.sidebar-scrim { position:fixed; inset:0; z-index:39; border:0; background:rgb(0 0 0 / .56); }
	.confidential-sidebar { position:fixed; inset:0 auto 0 0; z-index:40; display:none; width:min(20rem,calc(100vw - 2rem)); flex-direction:column; border-right:1px solid #3b414a; background:#202224; color:#d8dde6; padding:.9rem .55rem .75rem; box-shadow:14px 0 35px rgb(0 0 0 / .42); }
	.confidential-sidebar.open { display:flex; }.sidebar-head{position:relative;display:flex;align-items:center;min-height:3.5rem;padding:.1rem .4rem .85rem;border-bottom:1px solid #343a44}.brand{display:flex;align-items:center;gap:.75rem;font-size:1.1rem;font-weight:650;color:#f1f4f8}.brand-mark,.model-mark{display:grid;place-items:center;background:#272a2e;color:#eef3fa;border-radius:.45rem;font-weight:800}.brand-mark{width:2.3rem;height:2.3rem;font-size:.78rem}.collapse-desktop{margin-left:auto;border:0;background:transparent;color:#aeb8c7;padding:.45rem}.close-mobile{position:absolute;top:.25rem;right:.3rem;display:grid;place-items:center;border:0;border-radius:.4rem;background:transparent;color:#b8c1ce;padding:.3rem}.new-chat,.side-action{display:flex;align-items:center;gap:.8rem;width:100%;border:0;border-radius:.7rem;background:#e7edf7;color:#1d232c;padding:.8rem 1rem;margin-top:.85rem;font-size:1rem;text-align:left;font-weight:500;text-decoration:none}.side-action{margin-top:.25rem;background:transparent;color:#c8d0db;padding:.7rem 1rem}.new-chat:hover{background:#f3f6fb}.side-action:hover,.conversation:hover,.model-row:hover{background:#2b3037}.search-box{display:flex;align-items:center;gap:.7rem;margin:.18rem .25rem .65rem;padding:.55rem .7rem;color:#b6c0cf}.search-box input{min-width:0;width:100%;border:0;outline:0;background:transparent;color:#eef2f8;font:inherit;font-size:1rem}.search-box input::placeholder{color:#b6c0cf}.section-title,.history-title{display:flex;align-items:center;justify-content:space-between;padding:.85rem .95rem .38rem;color:#b7bfca;font-size:.8rem}.model-list{padding-bottom:.15rem}.model-row{display:flex;align-items:center;gap:.75rem;margin:.05rem .3rem;border-radius:.55rem;padding:.62rem .7rem;color:#c7d0dd;font-size:1rem}.model-mark{width:1.7rem;height:1.7rem;font-size:.54rem}.history{min-height:0;flex:1;overflow:auto;margin-top:.35rem}.history-title span:last-child{color:#7f8b99;font-size:.62rem;text-transform:uppercase;letter-spacing:.08em}.empty{margin:.2rem 1rem;color:#98a3b1;font-size:.78rem;line-height:1.45}.conversation{display:block;width:calc(100% - .6rem);overflow:hidden;border:0;border-radius:.5rem;background:transparent;color:#d1d8e2;padding:.62rem .8rem;margin:0 .3rem;text-align:left;text-overflow:ellipsis;white-space:nowrap;font-size:.85rem}.sidebar-footer{position:relative;border-top:1px solid #343a44;padding-top:.65rem}.account{display:flex;align-items:center;gap:.65rem;width:100%;border:0;border-radius:.75rem;background:#2b323e;color:#e5eaf1;padding:.65rem .72rem;text-align:left}.account>span:nth-child(2){display:grid;min-width:0;flex:1;gap:.08rem}.account strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.9rem}.account small{overflow:hidden;color:#aeb8c5;font-size:.7rem;text-overflow:ellipsis;white-space:nowrap}.avatar{display:grid;place-items:center;width:2.35rem;height:2.35rem;flex:0 0 auto;border-radius:50%;background:#0587d1;color:white;font-size:1rem;font-weight:700}.account-menu{position:absolute;z-index:2;bottom:calc(100% + .45rem);left:.15rem;right:.15rem;display:grid;gap:.7rem;max-height:calc(100vh - 1rem);overflow:auto;border:1px solid #5b6470;border-radius:1rem;background:#2b2e32;padding:.85rem;box-shadow:0 15px 40px rgb(0 0 0 / .55)}.account-heading{display:flex;align-items:center;gap:.65rem}.account-heading strong{flex:1;font-size:1rem}.account-heading button{border:0;background:transparent;color:#aeb8c5;font-size:1.5rem}.usage-state{margin:0;color:#c7d0da;line-height:1.4;font-size:.8rem}.usage-card{display:grid;gap:.72rem;border-top:1px solid #444a52;padding-top:.75rem}.usage-heading{display:flex;align-items:center;justify-content:space-between;font-size:.72rem;font-weight:750;letter-spacing:.07em;color:#eef1f6}.usage-heading span:last-child{color:#aeb8c5;font-size:.62rem;font-weight:500;letter-spacing:0}.remaining{display:grid;gap:.06rem}.remaining strong{font-size:1rem;color:#fff}.remaining span{font-size:.7rem;color:#aeb8c5}.usage-row{display:grid;gap:.35rem}.usage-row>div{display:flex;justify-content:space-between;gap:.5rem;font-size:.74rem;color:#d4dae2}.usage-row b{font-weight:500;color:#e5eaf1}.usage-row i{display:block;height:.36rem;overflow:hidden;border-radius:999px;background:#464a4f}.usage-row em{display:block;height:100%;border-radius:inherit;background:#a1a7af}.usage-reset{display:grid;gap:.23rem;color:#b9c0ca;font-size:.7rem;line-height:1.35}.account-action{display:flex;align-items:center;gap:.7rem;border:0;border-top:1px solid #40454d;background:transparent;color:#e0e4eb;padding:.68rem .1rem;font:inherit;text-decoration:none;text-align:left;font-size:.95rem}.signout{color:#e0e4eb;cursor:pointer}@media(min-width:768px){.mobile-nav,.sidebar-scrim,.close-mobile{display:none}.confidential-sidebar{display:flex;width:17.5rem;box-shadow:none}.collapse-desktop{display:block}}@media(max-width:767px){.collapse-desktop{display:none}}
</style>
