import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

const output = resolve(process.argv[2] ?? 'static/release.json');
const required = ['RELEASE_TAG', 'RELEASE_COMMIT', 'RELEASE_REPOSITORY'];
for (const name of required) {
	if (!process.env[name]) throw new Error(`${name} is required to write release provenance.`);
}
const sourceTree = execFileSync('git', ['ls-tree', '-r', '--full-tree', process.env.RELEASE_COMMIT], {
	encoding: 'utf8'
});
const manifest = {
	schema: 1,
	status: 'released',
	repository: process.env.RELEASE_REPOSITORY,
	tag: process.env.RELEASE_TAG,
	commit: process.env.RELEASE_COMMIT,
	source_tree_sha256: createHash('sha256').update(sourceTree).digest('hex'),
	built_at: new Date().toISOString()
};
mkdirSync(dirname(output), { recursive: true });
writeFileSync(output, `${JSON.stringify(manifest, null, 2)}\n`);
