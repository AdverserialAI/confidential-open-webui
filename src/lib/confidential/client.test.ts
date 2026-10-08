import { afterEach, describe, expect, it, vi } from 'vitest';

import { isConfidentialModel, sendConfidentialCompletionStream } from './client';

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('confidential model registration', () => {
	it('enables the browser-only path only for canonical explicitly marked models', () => {
		expect(
			isConfidentialModel({
				id: 'lordx64/cyberglm',
				info: { meta: { confidential_transport: true } }
			})
		).toBe(true);
		expect(isConfidentialModel({ id: 'cyberglm', info: { meta: { confidential_transport: true } } })).toBe(
			false
		);
		expect(isConfidentialModel({ id: 'lordx64/cyberglm', info: { meta: {} } })).toBe(false);
	});
});

describe('confidential signed streaming', () => {
	it('renders reasoning and answer deltas while verifying the final stream receipt', async () => {
		const body = [
			'data: {"choices":[{"delta":{"reasoning_content":"I will inspect the evidence. "}}]}\n\n',
			'data: {"choices":[{"delta":{"content":"Verified answer"}}]}\n\n',
			'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2}}\n\n',
			'data: {"adversarial_receipt":"test-receipt"}\n\n',
			'data: [DONE]\n\n'
		];
		const encoder = new TextEncoder();
		const stream = new ReadableStream<Uint8Array>({
			start(controller) {
				for (const chunk of body) controller.enqueue(encoder.encode(chunk));
				controller.close();
			}
		});
		const verifyInferenceReceipt = vi.fn(async () => undefined);
		vi.stubGlobal('window', {
			location: { origin: 'https://chat.adverserial.ai' },
			AdverserialConfidentialSDK: { verifyInferenceReceipt }
		});
		vi.stubGlobal(
			'fetch',
			vi.fn(async () =>
				new Response(JSON.stringify({ entitlement: 'one-use-grant', max_output_tokens: 128 }), {
					status: 200,
					headers: { 'content-type': 'application/json' }
				})
			)
		);

		const updates: Array<{ content?: string; reasoning?: string }> = [];
		await sendConfidentialCompletionStream(
			{
				modelId: 'lordx64/cyberglm',
				config: {
					api_base_url: 'https://cc-api.adverserial.ai/v1',
					max_output_tokens: 128,
					receipt_issuer: 'https://verify.adverserial.ai',
					receipt_audience: 'https://chat.adverserial.ai'
				},
				proof: {
					expiresEpoch: Date.now() / 1000 + 60,
					tlsSpkiSha256: 'sha256:test',
					attestationStateDigest: 'sha256:evidence'
				},
				trustedReceiptKeys: {},
				client: {
					fetchWithEntitlement: () => async () =>
						new Response(stream, { headers: { 'content-type': 'text/event-stream' } })
				}
			} as any,
			'session-token',
			{ model: 'lordx64/cyberglm', messages: [{ role: 'user', content: 'hello' }] },
			(update) => updates.push(update)
		);

		expect(updates).toContainEqual({ reasoning: 'I will inspect the evidence. ' });
		expect(updates).toContainEqual({ content: 'Verified answer' });
		expect(verifyInferenceReceipt).toHaveBeenCalledWith(
			expect.objectContaining({
				receipt: 'test-receipt',
				responseBody:
					'{"choices":[{"delta":{"reasoning_content":"I will inspect the evidence. "}}]}{"choices":[{"delta":{"content":"Verified answer"}}]}{"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2}}[DONE]'
			})
		);
	});

	it('accepts an equivalent signed receipt header while still authenticating every streamed byte', async () => {
		vi.resetModules();
		const { sendConfidentialCompletionStream } = await import('./client');
		const encoder = new TextEncoder();
		const stream = new ReadableStream<Uint8Array>({
			start(controller) {
				controller.enqueue(encoder.encode('data: {\"choices\":[{\"delta\":{\"content\":\"Verified answer\"}}]}\n\n'));
				controller.enqueue(encoder.encode('data: [DONE]\n\n'));
				controller.close();
			}
		});
		const verifyInferenceReceipt = vi.fn(async () => undefined);
		vi.stubGlobal('window', {
			location: { origin: 'https://chat.adverserial.ai' },
			AdverserialConfidentialSDK: { verifyInferenceReceipt }
		});
		vi.stubGlobal(
			'fetch',
			vi.fn(async () =>
				new Response(JSON.stringify({ entitlement: 'one-use-grant', max_output_tokens: 128 }), {
					status: 200,
					headers: { 'content-type': 'application/json' }
				})
			)
		);

		await sendConfidentialCompletionStream(
			{
				modelId: 'lordx64/cyberglm',
				config: {
					api_base_url: 'https://cc-api.adverserial.ai/v1',
					max_output_tokens: 128,
					receipt_issuer: 'https://verify.adverserial.ai',
					receipt_audience: 'https://chat.adverserial.ai'
				},
				proof: {
					expiresEpoch: Date.now() / 1000 + 60,
					tlsSpkiSha256: 'sha256:test',
					attestationStateDigest: 'sha256:evidence'
				},
				trustedReceiptKeys: {},
				client: {
					fetchWithEntitlement: () => async () =>
						new Response(stream, {
							headers: {
								'content-type': 'text/event-stream',
								'x-adverserial-receipt': 'header-receipt'
							}
						})
				}
			} as any,
			'session-token',
			{ model: 'lordx64/cyberglm', messages: [{ role: 'user', content: 'hello' }] },
			() => undefined
		);

		expect(verifyInferenceReceipt).toHaveBeenCalledWith(
			expect.objectContaining({ receipt: 'header-receipt', responseBody: '{\"choices\":[{\"delta\":{\"content\":\"Verified answer\"}}]}[DONE]' })
		);
	});
});
