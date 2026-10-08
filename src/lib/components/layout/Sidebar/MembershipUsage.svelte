<script lang="ts">
 import { onMount } from 'svelte';
 let status: any = null;
 let failed = false;
 const limits = [
  ['credit_day', 'Credits today', 'credits'],
  ['credit_week', 'Credits this week', 'credits'],
  ['output_day', 'Output today', 'tokens'],
  ['output_week', 'Output this week', 'tokens']
 ];
 const number = (n: number, unit: string) => n.toLocaleString(undefined, { maximumFractionDigits: unit === 'tokens' ? 0 : 2 });
 const reset = (date: string) => new Date(date).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
 async function refresh() {
  try {
   const r = await fetch('https://billing.adverserial.ai/account/usage-status', { headers: { Authorization: `Bearer ${localStorage.token}` }, cache: 'no-store' });
   if (!r.ok) throw new Error('Unavailable');
   const next = await r.json();
   if (typeof next.member !== 'boolean' || (next.member && limits.some(([key]) => !Number.isFinite(next[`${key}_used`]) || !(next[`${key}_cap`] > 0)))) throw new Error('Invalid usage');
   status = next; failed = false;
  } catch { failed = true; }
 }
 onMount(() => { refresh(); const timer = setInterval(refresh, 30000); return () => clearInterval(timer); });
</script>

{#if failed}
 <div class="meter-message" role="status">Usage unavailable. <button on:click={refresh}>Retry</button></div>
{:else if status === null}
 <div class="meter-message" role="status">Loading membership usage…</div>
{:else if status.member}
 <section class="membership-usage" aria-label="Membership allowance">
  <strong>{status.display_name}</strong>
  {#each limits as [key, label, unit]}
   <div class="usage-row">
    <div class="usage-label"><span>{label}</span><span>{number(status[`${key}_used`], unit)} / {number(status[`${key}_cap`], unit)}</span></div>
    <progress aria-label={`${label} (${unit})`} max={status[`${key}_cap`]} value={Math.min(status[`${key}_cap`], Math.max(0, status[`${key}_used`]))}></progress>
   </div>
  {/each}
  <p>Daily reset: {reset(status.daily_reset_at)}<br/>Weekly reset: {reset(status.weekly_reset_at)}</p>
  <p>Paid overages: {status.overage_enabled ? 'On' : 'Off'}. Active requests may reserve remaining allowance.</p>
 </section>
{/if}
<style>
 .membership-usage{padding:12px 8px;border-top:1px solid #8883;margin-top:8px;font-size:11px;line-height:1.5;max-width:100%}
 strong{font-size:11px;letter-spacing:.035em}.usage-row{margin-top:10px}.usage-label{display:flex;flex-wrap:wrap;justify-content:space-between;gap:2px 8px;font-variant-numeric:tabular-nums}
 progress{display:block;width:100%;height:5px;margin-top:4px;accent-color:#7796b0;border:0;border-radius:3px;overflow:hidden}progress::-webkit-progress-bar{background:#8883}progress::-webkit-progress-value{background:#7796b0}progress::-moz-progress-bar{background:#7796b0}p{margin-top:10px;opacity:.75}.meter-message{padding:12px 8px;font-size:11px}button{text-decoration:underline;min-height:32px}
</style>
