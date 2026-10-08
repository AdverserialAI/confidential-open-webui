<script lang="ts">
 import { onMount } from 'svelte';
 import { goto } from '$app/navigation';
 import { page } from '$app/stores';
 import { getSessionUser } from '$lib/apis/auths';
 let error = '';
 onMount(async () => {
  const plan = $page.url.searchParams.get('plan');
  if (plan && !['foothold', 'hacker_manifesto', 'godmod3'].includes(plan)) {
   error = 'This membership plan is not available. Please choose a plan again.';
   return;
  }
  const destination = '/billing' + (plan ? '?plan=' + encodeURIComponent(plan) : '');
  const signIn = () => goto('/auth?redirect=' + encodeURIComponent(destination), { replaceState: true });
  const token = localStorage.getItem('token');
  if (!token) { await signIn(); return; }
  let session;
  try { session = await getSessionUser(token); }
  catch { error = 'We could not verify your session. Please sign in again to continue.'; return; }
  if (!session) { await signIn(); return; }
  // POST credentials to the fixed billing origin, never in a URL or redirect parameter.
  const form = document.createElement('form');
  form.method = 'POST';
  form.action = 'https://billing.adverserial.ai/' + (plan ? 'membership/session' : 'account/session');
  for (const [name, value] of Object.entries({ owui_token: token, ...(plan ? { plan } : {}) })) {
   const input = document.createElement('input');
   input.type = 'hidden'; input.name = name; input.value = value;
   form.appendChild(input);
  }
  document.body.appendChild(form);
  form.submit();
 });
</script>

<svelte:head><title>Continue to billing — Adverserial AI</title><meta name="robots" content="noindex" /></svelte:head>
<main class="min-h-screen flex items-center justify-center px-6 bg-white dark:bg-gray-950">
 <div class="max-w-md text-center space-y-4">
  <h1 class="text-2xl font-semibold">{error ? 'Unable to continue' : 'Connecting your account'}</h1>
  <p class="text-gray-600 dark:text-gray-300" role="status">{error || 'Taking you securely to billing. Please keep this page open.'}</p>
  {#if error}
   <a class="underline block" href={'/auth?redirect=' + encodeURIComponent($page.url.pathname + $page.url.search)}>Sign in again</a>
   <a class="underline block" href="https://billing.adverserial.ai/membership">View memberships</a>
  {/if}
 </div>
</main>
