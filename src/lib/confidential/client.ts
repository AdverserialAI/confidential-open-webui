/**
 * Browser-only confidential inference path.
 *
 * Open WebUI keeps the sign-in session.  This module uses that session only
 * for a short-lived billing entitlement; it verifies the live runtime, encrypts
 * the request with EHBP, and routes ciphertext through the same-origin relay.
 * Do not add a plaintext fallback here: a failed proof must leave the prompt
 * unsent.
 */

import { writable } from 'svelte/store';

import { WEBUI_BASE_URL } from '$lib/constants';
import { confidentialVerificationConfig } from './verification';

type JsonRecord = Record<string, unknown>;

type ConfidentialConfig = {
	api_base_url: string;
	attestation_url: string;
	policy_url: string;
	billing_base_url: string;
	receipt_issuer: string;
	receipt_audience: string;
	max_output_tokens: number;
	models: Array<{ id: string }>;
};

type RuntimeProof = {
	modelId: string;
	hardwareVerifier?: string;
	tee?: string;
	gpu?: string;
	tlsSpkiSha256: string;
	attestationStateDigest: string;
	expiresEpoch: number;
};

type VerifiedClient = {
	verified: boolean;
	reason?: string;
	proof?: RuntimeProof;
	fetchWithEntitlement: (entitlement: string) => typeof fetch;
};

type ConfidentialSdk = {
	createVerifiedOpenAI: (options: JsonRecord) => Promise<VerifiedClient>;
	createPhalaNVIDIAVerifier: (options: { minimumGPUCount: number }) => unknown;
	verifyInferenceReceipt: (options: JsonRecord) => Promise<void>;
};

export type ConfidentialRuntimeState =
	| { status: 'idle' }
	| { status: 'verifying'; modelId: string }
	| { status: 'verified'; proof: RuntimeProof; policy: JsonRecord }
	| { status: 'failed'; modelId: string; reason: string };

export const confidentialRuntime = writable<ConfidentialRuntimeState>({ status: 'idle' });

type Session = {
	modelId: string;
	config: ConfidentialConfig;
	policy: JsonRecord;
	client: VerifiedClient;
	proof: RuntimeProof;
	trustedReceiptKeys: JsonRecord;
	verificationOptions: JsonRecord;
};

const browserSdkPath = '/confidential/adverserial-confidential-sdk.js';
let sdkLoad: Promise<ConfidentialSdk> | null = null;

const isRecord = (value: unknown): value is JsonRecord =>
	typeof value === 'object' && value !== null && !Array.isArray(value);

const responseError = async (response: Response, fallback: string) => {
	const body = await response.json().catch(() => null);
	if (isRecord(body)) {
		const detail = body.detail;
		if (typeof detail === 'string') return detail;
		if (isRecord(body.error) && typeof body.error.message === 'string') return body.error.message;
	}
	return fallback;
};

const endpointOrigin = (value: string) => {
	const url = new URL(value);
	if (url.protocol !== 'https:') throw new Error('The confidential endpoint must use HTTPS.');
	return url.origin;
};

const base64UrlNonce = () => {
	const bytes = crypto.getRandomValues(new Uint8Array(32));
	let output = '';
	for (const byte of bytes) output += String.fromCharCode(byte);
	return btoa(output).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/u, '');
};

const canonicalModelId = (value: unknown): value is string =>
	typeof value === 'string' && /^[a-z0-9][a-z0-9._-]{0,127}\/[a-z0-9][a-z0-9._-]{0,127}$/.test(value);

const fetchConfig = async (sessionToken: string): Promise<ConfidentialConfig> => {
	const response = await fetch(`${WEBUI_BASE_URL}/api/v1/confidential/config`, {
		credentials: 'include',
		cache: 'no-store',
		headers: { authorization: `Bearer ${sessionToken}`, accept: 'application/json' }
	});
	if (!response.ok) throw new Error(await responseError(response, 'Confidential client configuration is unavailable.'));
	const config = (await response.json()) as ConfidentialConfig;
	if (
		!isRecord(config) ||
		!Array.isArray(config.models) ||
		!config.models.every((model) => isRecord(model) && canonicalModelId(model.id)) ||
		!canonicalModelId(config.models[0]?.id) ||
		!Number.isInteger(config.max_output_tokens) ||
		config.max_output_tokens < 1
	) {
		throw new Error('Confidential client configuration is invalid.');
	}
	endpointOrigin(config.api_base_url);
	endpointOrigin(config.attestation_url);
	endpointOrigin(config.policy_url);
	endpointOrigin(config.billing_base_url);
	endpointOrigin(config.receipt_issuer);
	endpointOrigin(config.receipt_audience);
	return config;
};

const loadSdk = (): Promise<ConfidentialSdk> => {
	if (sdkLoad) return sdkLoad;
	sdkLoad = new Promise((resolve, reject) => {
		const existing = (window as typeof window & { AdverserialConfidentialSDK?: ConfidentialSdk })
			.AdverserialConfidentialSDK;
		if (existing) {
			resolve(existing);
			return;
		}
		const script = document.createElement('script');
		script.src = browserSdkPath;
		script.async = true;
		script.onload = () => {
			const sdk = (window as typeof window & { AdverserialConfidentialSDK?: ConfidentialSdk })
				.AdverserialConfidentialSDK;
			if (!sdk?.createVerifiedOpenAI || !sdk.createPhalaNVIDIAVerifier || !sdk.verifyInferenceReceipt) {
				reject(new Error('The pinned confidential verification SDK is unavailable.'));
				return;
			}
			resolve(sdk);
		};
		script.onerror = () => reject(new Error('The pinned confidential verification SDK could not be loaded.'));
		document.head.append(script);
	});
	return sdkLoad;
};

const relayFetch = (sessionToken: string): typeof fetch => {
	return async (input: RequestInfo | URL, init?: RequestInit) => {
		const request = input instanceof Request ? input : new Request(input, init);
		const target = new URL(request.url);
		if (!target.pathname.startsWith('/v1/')) return fetch(request);

		const headers = new Headers(request.headers);
		headers.set('x-openwebui-authorization', `Bearer ${sessionToken}`);
		return fetch(`${WEBUI_BASE_URL}/api/v1/confidential/relay${target.pathname.slice('/v1'.length)}${target.search}`, {
			method: request.method,
			credentials: 'include',
			cache: 'no-store',
			headers,
			body: request.body,
			duplex: request.body ? 'half' : undefined
		} as RequestInit);
	};
};

const loadPolicy = async (config: ConfidentialConfig, modelId: string) => {
	const response = await fetch(config.policy_url, {
		credentials: 'omit',
		cache: 'no-store',
		headers: { accept: 'application/json' }
	});
	if (!response.ok) throw new Error(`The public runtime policy returned ${response.status}.`);
	const policy = (await response.json()) as JsonRecord;
	if (!isRecord(policy) || policy.status !== 'active' || policy.model_id !== modelId) {
		throw new Error('No active public policy matches the selected model.');
	}
	if (!isRecord(policy.receipt_keys) || Object.keys(policy.receipt_keys).length === 0) {
		throw new Error('The active policy has no attestation receipt keys.');
	}
	const runtime = isRecord(policy.allowed_runtime) ? policy.allowed_runtime : null;
	const minimumGPUCount = runtime?.minimum_gpu_count;
	if (typeof minimumGPUCount !== 'number' || !Number.isInteger(minimumGPUCount) || minimumGPUCount < 1) {
		throw new Error('The active policy has no valid GPU requirement.');
	}
	return { policy, trustedReceiptKeys: policy.receipt_keys, minimumGPUCount };
};

export const isConfidentialModel = (model: any) =>
	Boolean(
		model?.id &&
		canonicalModelId(model.id) &&
		// `confidential_transport` is the model-registration switch for the new
		// browser transport. The prior verification metadata remains accepted so
		// existing confidential model entries keep working during migration.
		(model.info?.meta?.confidential_transport === true || confidentialVerificationConfig(model))
	);

export const verifyConfidentialRuntime = async (modelId: string, sessionToken: string): Promise<Session> => {
	confidentialRuntime.set({ status: 'verifying', modelId });
	try {
		const [config, sdk] = await Promise.all([fetchConfig(sessionToken), loadSdk()]);
		if (!config.models.some((model) => model.id === modelId)) {
			throw new Error('This model is not enabled for confidential inference.');
		}
		const { policy, trustedReceiptKeys, minimumGPUCount } = await loadPolicy(config, modelId);
		const verificationOptions: JsonRecord = {
			baseURL: config.api_base_url,
			expectedModelId: modelId,
			trustedReceiptKeys,
			issuer: config.receipt_issuer,
			audience: config.receipt_audience,
			expectedEndpoint: endpointOrigin(config.api_base_url),
			expectedModelDigest: typeof policy.model_artifact_digest === 'string' ? policy.model_artifact_digest : undefined,
			expectedRuntimeDigest: typeof policy.runtime_image_digest === 'string' ? policy.runtime_image_digest : undefined,
			attestationUrl: config.attestation_url,
			verifyHardwareEvidence: sdk.createPhalaNVIDIAVerifier({ minimumGPUCount }),
			fetchImpl: relayFetch(sessionToken)
		};
		const client = await sdk.createVerifiedOpenAI(verificationOptions);
		if (!client.verified || !client.proof) {
			throw new Error(client.reason || 'The independent hardware verifier did not accept the runtime evidence.');
		}
		const session = { modelId, config, policy, client, proof: client.proof, trustedReceiptKeys, verificationOptions };
		confidentialRuntime.set({ status: 'verified', proof: client.proof, policy });
		return session;
	} catch (error) {
		const reason = error instanceof Error ? error.message : 'Runtime verification failed unexpectedly.';
		confidentialRuntime.set({ status: 'failed', modelId, reason });
		throw new Error(reason);
	}
};

const requestEntitlement = async (
	session: Session,
	sessionToken: string,
	requestBody: string
): Promise<{ entitlement: string; max_output_tokens: number }> => {
	const response = await fetch(`${WEBUI_BASE_URL}/api/v1/confidential/entitlements`, {
		method: 'POST',
		credentials: 'include',
		headers: {
			authorization: `Bearer ${sessionToken}`,
			accept: 'application/json',
			'content-type': 'application/json'
		},
		body: JSON.stringify({
			model: session.modelId,
			// Billing treats this as a conservative bound.  The encrypted body is
			// not included in the entitlement request.
			max_input_tokens: new TextEncoder().encode(requestBody).byteLength,
			max_output_tokens: session.config.max_output_tokens,
			endpoint_spki_sha256: session.proof.tlsSpkiSha256
		})
	});
	if (!response.ok) throw new Error(await responseError(response, 'Billing could not issue a confidential entitlement.'));
	const grant = (await response.json()) as { entitlement?: unknown; max_output_tokens?: unknown };
	if (typeof grant.entitlement !== 'string' || !Number.isInteger(grant.max_output_tokens)) {
		throw new Error('Billing returned an invalid confidential entitlement.');
	}
	return grant as { entitlement: string; max_output_tokens: number };
};

export const sendConfidentialCompletion = async (
	session: Session,
	sessionToken: string,
	draft: JsonRecord
): Promise<{ completion: JsonRecord; receipt: string }> => {
	if (session.proof.expiresEpoch <= Date.now() / 1000) {
		throw new Error('The verification proof expired. Verify the runtime again before sending a prompt.');
	}
	const nonce = base64UrlNonce();
	const requested = JSON.stringify({ ...draft, stream: false, max_tokens: session.config.max_output_tokens });
	const grant = await requestEntitlement(session, sessionToken, requested);
	const body = JSON.stringify({ ...draft, stream: false, max_tokens: grant.max_output_tokens });
	const response = await session.client.fetchWithEntitlement(grant.entitlement)(
		`${session.config.api_base_url}/chat/completions`,
		{
			method: 'POST',
			credentials: 'omit',
			headers: { 'content-type': 'application/json', 'x-adverserial-nonce': nonce },
			body
		}
	);
	const responseBody = await response.text();
	if (!response.ok) throw new Error(`Confidential API request failed (${response.status}).`);
	const receipt = response.headers.get('x-adverserial-receipt');
	if (!receipt) throw new Error('The confidential runtime did not return a signed inference receipt.');
	const sdk = await loadSdk();
	await sdk.verifyInferenceReceipt({
		receipt,
		trustedReceiptKeys: session.trustedReceiptKeys,
		issuer: session.config.receipt_issuer,
		audience: session.config.receipt_audience,
		modelId: session.modelId,
		requestNonce: nonce,
		requestBody: body,
		responseBody,
		tlsSpkiSha256: session.proof.tlsSpkiSha256,
		attestationStateDigest: session.proof.attestationStateDigest
	});
	const completion = JSON.parse(responseBody) as JsonRecord;
	return { completion, receipt };
};
