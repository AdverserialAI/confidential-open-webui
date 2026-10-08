import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const source = readFileSync('src/routes/billing/+page.svelte', 'utf8').split('<script lang="ts">')[1].split('</script>')[0].replace(/^\s*import .*;$/gm, '');
const js = ts.transpileModule(source, {compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText;
async function run(plan, token, valid=true) {
 const result={}; let mount;
 const context={
  onMount: f=>mount=f, goto: async url=>{result.redirect=url},
  $page:{url:new URL('https://chat.adverserial.ai/billing'+(plan?'?plan='+plan:''))},
  localStorage:{getItem:()=>token},
  getSessionUser:async()=>valid?{id:'test-owner'}:null,
  document:{createElement:tag=>tag==='form'?{fields:[],appendChild(input){this.fields.push(input)},submit(){result.form=this}}:{},body:{appendChild(){}}}
 };
 vm.runInNewContext(js,context); await mount(); return result;
}
for(const plan of ['foothold','hacker_manifesto','godmod3']) {
 const anonymous=await run(plan,null);
 assert.equal(anonymous.redirect,'/auth?redirect='+encodeURIComponent('/billing?plan='+plan));
 const signedIn=await run(plan,'private-test-token');
 assert.equal(signedIn.form.action,'https://billing.adverserial.ai/membership/session');
 assert.equal(signedIn.form.method,'POST');
 assert.equal(signedIn.form.fields.find(x=>x.name==='plan').value,plan);
 assert.equal(signedIn.form.fields.find(x=>x.name==='owui_token').value,'private-test-token');
 assert.equal(signedIn.form.action.includes('private-test-token'),false);
}
assert.equal((await run(null,'test')).form.action,'https://billing.adverserial.ai/account/session');
assert.equal((await run('invalid','test')).form,undefined);
assert.equal((await run('foothold','expired',false)).redirect,'/auth?redirect=%2Fbilling%3Fplan%3Dfoothold');
console.log('Billing handoff tests passed: signup/login return paths, three plans, POST-only credentials, account management, invalid plan/session.');
