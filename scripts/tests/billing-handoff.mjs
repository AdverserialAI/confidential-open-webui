import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = readFileSync('src/routes/billing/+page.svelte', 'utf8')
	.split('<script lang="ts">')[1]
	.split('</script>')[0]
	.replace(/^\s*import .*;$/gm, '');
const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
const handoff = 'eyJhbGciOiJFZERTQSJ9.eyJzdWIiOiJ0ZXN0QGV4YW1wbGUuY29tIn0.signature';

async function run(plan, signedIn = true, issuedHandoff = handoff) {
	const result = {};
	let mount;
	const context = {
		onMount: (callback) => (mount = callback),
		goto: async (url) => {
			result.redirect = url;
		},
		$page: { url: new URL(`https://chat.adverserial.ai/billing${plan ? `?plan=${plan}` : ''}`) },
		getSessionUser: async () => (signedIn ? { id: 'test-owner' } : null),
		fetch: async (url, init) => {
			result.handoffRequest = { url, init };
			return { ok: Boolean(issuedHandoff), json: async () => ({ handoff: issuedHandoff }) };
		},
		document: {
			createElement: (tag) =>
				tag === 'form'
					? { fields: [], appendChild(input) { this.fields.push(input); }, submit() { result.form = this; } }
					: {},
			body: { appendChild() {} }
		}
	};
	vm.runInNewContext(js, context);
	await mount();
	return result;
}

for (const plan of ['foothold', 'hacker_manifesto', 'godmod3']) {
	const anonymous = await run(plan, false);
	assert.equal(anonymous.redirect, `/auth?redirect=${encodeURIComponent(`/billing?plan=${plan}`)}`);
	const signedIn = await run(plan);
	assert.equal(signedIn.handoffRequest.url, '/api/v1/confidential/billing-handoff');
	assert.equal(JSON.parse(signedIn.handoffRequest.init.body).destination, plan);
	assert.equal(signedIn.form.action, 'https://billing.adverserial.ai/account/session/exchange');
	assert.equal(signedIn.form.method, 'POST');
	assert.deepEqual(signedIn.form.fields.map((field) => field.name), ['handoff']);
	assert.equal(signedIn.form.fields[0].value, handoff);
}

const account = await run(null);
assert.equal(JSON.parse(account.handoffRequest.init.body).destination, 'account');
assert.equal(account.form.fields.length, 1);
assert.equal((await run('invalid')).form, undefined);
assert.equal((await run('foothold', true, '')).form, undefined);
console.log('Billing handoff tests passed: cookie-authenticated signed handoff, fixed destinations, and top-level exchange only.');
