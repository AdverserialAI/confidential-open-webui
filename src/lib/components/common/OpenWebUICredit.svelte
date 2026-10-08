<script lang="ts">
	const openSecurityExplainer = () => {
		window.dispatchEvent(new Event('adverserial:open-verification-process'));
	};
</script>

<footer class="py-2 text-center text-xs text-gray-600 dark:text-gray-300">
	Built with
	<a
		href="https://openwebui.com/"
		target="_blank"
		rel="noopener noreferrer"
		class="font-medium underline underline-offset-2"
	>Open WebUI</a> · Customized by Adverserial AI
	<span class="px-1 text-gray-400 dark:text-gray-500">·</span>
	<button
		type="button"
		on:click={openSecurityExplainer}
		class="font-medium text-gray-700 underline underline-offset-2 transition hover:text-gray-950 dark:text-gray-200 dark:hover:text-white"
		aria-haspopup="dialog"
	>
		How secure is this chat?
	</button>
</footer>
