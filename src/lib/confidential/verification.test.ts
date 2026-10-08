import { describe, expect, it } from 'vitest';

import {
	confidentialVerificationConfig,
	verificationEvidenceDigest,
	verifyConfidentialEndpoint,
	type ConfidentialVerificationConfig
} from './verification';

const encoder = new TextEncoder();
const encodeBase64Url = (bytes: Uint8Array): string => {
	let binary = '';
	for (const byte of bytes) binary += String.fromCharCode(byte);
	return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/u, '');
};

const makeJws = async (claims: Record<string, unknown>, privateKey: CryptoKey): Promise<string> => {
	const header = encodeBase64Url(encoder.encode(JSON.stringify({ alg: 'ES256', kid: 'test-key' })));
	const payload = encodeBase64Url(encoder.encode(JSON.stringify(claims)));
	const signingInput = `${header}.${payload}`;
	const signature = await crypto.subtle.sign(
		{ name: 'ECDSA', hash: 'SHA-256' },
		privateKey,
		encoder.encode(signingInput)
	);
	return `${signingInput}.${encodeBase64Url(new Uint8Array(signature))}`;
};

describe('confidential verification receipt', () => {
	it('only accepts a signed receipt bound to the fresh nonce and evidence', async () => {
		const keyPair = (await crypto.subtle.generateKey(
			{ name: 'ECDSA', namedCurve: 'P-256' },
			true,
			['sign', 'verify']
		)) as CryptoKeyPair;
		const publicKey = (await crypto.subtle.exportKey('jwk', keyPair.publicKey)) as JsonWebKey;
		const evidence = { tdx_quote: 'opaque-evidence', nvidia_eat: 'opaque-token' };
		const now = Date.parse('2026-10-02T12:00:00.000Z');
		const config: ConfidentialVerificationConfig = {
			attestationUrl: 'https://inference.example/attestation',
			verificationUrl: 'https://verify.adverserial.ai',
			receiptIssuer: 'https://verify.adverserial.ai',
			receiptAudience: 'https://chat.adverserial.ai',
			trustedReceiptKeys: { 'test-key': publicKey },
			expected: {
				modelId: 'lordx64/cyberglm',
				endpoint: 'https://inference.example'
			}
		};

		const result = await verifyConfidentialEndpoint(config, {
			now: () => now,
			fetchImpl: async (input) => {
				const nonce = new URL(input.toString()).searchParams.get('nonce');
				const receipt = await makeJws(
					{
						iss: config.receiptIssuer,
						aud: config.receiptAudience,
						nonce,
						verdict: 'verified',
						iat: now / 1000,
						exp: now / 1000 + 60,
						model_id: 'lordx64/cyberglm',
						endpoint: 'https://inference.example',
						evidence_sha256: await verificationEvidenceDigest(evidence)
					},
					keyPair.privateKey
				);
				return new Response(JSON.stringify({ evidence, verification_receipt: receipt }), {
					status: 200,
					headers: { 'content-type': 'application/json' }
				});
			}
		});

		expect(result.status).toBe('verified');
		if (result.status === 'verified') {
			expect(result.proof.modelId).toBe('lordx64/cyberglm');
			expect(result.proof.receiptKeyId).toBe('test-key');
			expect(result.proof.receiptDigest).toMatch(/^sha256:/);
		}
	});

	it('does not configure a model from incomplete or non-HTTPS metadata', () => {
		expect(
			confidentialVerificationConfig({
				id: 'lordx64/cyberglm',
				info: { meta: { confidential_verification: { attestation_url: 'http://example.test' } } }
			})
		).toBeNull();
	});
});
