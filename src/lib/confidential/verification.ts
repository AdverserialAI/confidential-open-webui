/**
 * Browser-side verifier for an Adverserial confidential-inference endpoint.
 *
 * The endpoint returns fresh raw attestation evidence and a compact ES256 JWS
 * receipt issued by verify.adverserial.ai. The receipt is only trusted after
 * this client verifies its signature with a model-specific pinned public key
 * and binds it to the nonce, endpoint, model, policy and evidence digest.
 *
 * This module deliberately does not accept a bare { verified: true } response.
 * A server must validate the hardware evidence before it signs a receipt.
 */

export type JsonRecord = Record<string, unknown>;

export type ConfidentialVerificationConfig = {
	attestationUrl: string;
	verificationUrl: string;
	receiptIssuer: string;
	receiptAudience: string;
	trustedReceiptKeys: Record<string, JsonWebKey>;
	expected: {
		modelId: string;
		endpoint?: string;
		modelDigest?: string;
		runtimeDigest?: string;
	};
};

export type VerifiedProof = {
	issuedAt: string;
	expiresAt: string;
	modelId: string;
	modelDigest?: string;
	runtimeDigest?: string;
	evidenceDigest: string;
	verificationUrl: string;
	receiptKeyId: string;
	receiptDigest: string;
};

export type VerificationResult =
	| { status: 'verified'; proof: VerifiedProof }
	| { status: 'failed'; reason: string };

type ReceiptClaims = {
	iss?: unknown;
	aud?: unknown;
	nonce?: unknown;
	verdict?: unknown;
	iat?: unknown;
	exp?: unknown;
	evidence_sha256?: unknown;
	model_id?: unknown;
	model_digest?: unknown;
	runtime_digest?: unknown;
	endpoint?: unknown;
};

type AttestationResponse = {
	evidence?: JsonRecord;
	verification_receipt?: string;
};

type VerifyOptions = {
	fetchImpl?: typeof fetch;
	now?: () => number;
};

const textEncoder = new TextEncoder();
const textDecoder = new TextDecoder();
const ONE_MINUTE_MS = 60_000;

// TypeScript's DOM declarations distinguish ArrayBuffer from ArrayBufferLike,
// while Uint8Array may be backed by either. WebCrypto needs a concrete copy.
const asArrayBuffer = (bytes: Uint8Array): ArrayBuffer => {
	const copy = new Uint8Array(bytes.byteLength);
	copy.set(bytes);
	return copy.buffer;
};

const asObject = (value: unknown): JsonRecord | null =>
	typeof value === 'object' && value !== null && !Array.isArray(value)
		? (value as JsonRecord)
		: null;

const asNonEmptyString = (value: unknown): string | null =>
	typeof value === 'string' && value.trim().length > 0 ? value : null;

const isHttpsUrl = (value: unknown): value is string => {
	if (typeof value !== 'string') return false;
	try {
		return new URL(value).protocol === 'https:';
	} catch {
		return false;
	}
};

const canonicalize = (value: unknown): string => {
	if (value === null || typeof value !== 'object') return JSON.stringify(value);
	if (Array.isArray(value)) return `[${value.map(canonicalize).join(',')}]`;

	const object = value as JsonRecord;
	return `{${Object.keys(object)
		.sort()
		.map((key) => `${JSON.stringify(key)}:${canonicalize(object[key])}`)
		.join(',')}}`;
};

const toBase64Url = (bytes: Uint8Array): string => {
	let binary = '';
	for (const byte of bytes) binary += String.fromCharCode(byte);
	return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/u, '');
};

const fromBase64Url = (value: string): Uint8Array => {
	const normalized = value.replaceAll('-', '+').replaceAll('_', '/');
	const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
	const binary = atob(padded);
	return Uint8Array.from(binary, (character) => character.charCodeAt(0));
};

const sha256 = async (value: string): Promise<string> => {
	const digest = await crypto.subtle.digest('SHA-256', asArrayBuffer(textEncoder.encode(value)));
	return `sha256:${toBase64Url(new Uint8Array(digest))}`;
};

const readCompactJws = (receipt: string) => {
	const parts = receipt.split('.');
	if (parts.length !== 3 || parts.some((part) => !part)) {
		throw new Error('The verification receipt is not a compact JWS.');
	}

	const header = asObject(JSON.parse(textDecoder.decode(fromBase64Url(parts[0]))));
	const claims = asObject(JSON.parse(textDecoder.decode(fromBase64Url(parts[1]))));
	if (!header || !claims) throw new Error('The verification receipt has an invalid JSON payload.');

	return { header, claims: claims as ReceiptClaims, signingInput: `${parts[0]}.${parts[1]}`, signature: parts[2] };
};

const verifyReceiptSignature = async (
	receipt: string,
	trustedReceiptKeys: Record<string, JsonWebKey>
): Promise<ReceiptClaims> => {
	const { header, claims, signingInput, signature } = readCompactJws(receipt);
	const algorithm = asNonEmptyString(header.alg);
	const keyId = asNonEmptyString(header.kid);
	if (algorithm !== 'ES256' || !keyId || !trustedReceiptKeys[keyId]) {
		throw new Error('The receipt is not signed by a configured ES256 verification key.');
	}

	const key = await crypto.subtle.importKey(
		'jwk',
		trustedReceiptKeys[keyId],
		{ name: 'ECDSA', namedCurve: 'P-256' },
		false,
		['verify']
	);
	const signatureValid = await crypto.subtle.verify(
		{ name: 'ECDSA', hash: 'SHA-256' },
		key,
		asArrayBuffer(fromBase64Url(signature)),
		asArrayBuffer(textEncoder.encode(signingInput))
	);
	if (!signatureValid) throw new Error('The verification receipt signature is invalid.');

	return { claims, keyId };
};

const asEpochSeconds = (value: unknown, label: string): number => {
	if (typeof value !== 'number' || !Number.isFinite(value)) {
		throw new Error(`The verification receipt is missing ${label}.`);
	}
	return value;
};

const hasAudience = (audience: unknown, expected: string): boolean =>
	typeof audience === 'string' ? audience === expected : Array.isArray(audience) && audience.includes(expected);

export const confidentialVerificationConfig = (
	model: { id?: string; info?: { meta?: Record<string, unknown> } } | null | undefined
): ConfidentialVerificationConfig | null => {
	const raw = asObject(model?.info?.meta?.confidential_verification);
	const expected = asObject(raw?.expected);
	const keys = asObject(raw?.trusted_receipt_keys);
	if (!raw || !expected || !keys) return null;

	const config: ConfidentialVerificationConfig = {
		attestationUrl: asNonEmptyString(raw.attestation_url) ?? '',
		verificationUrl: asNonEmptyString(raw.verification_url) ?? 'https://verify.adverserial.ai',
		receiptIssuer: asNonEmptyString(raw.receipt_issuer) ?? '',
		receiptAudience: asNonEmptyString(raw.receipt_audience) ?? '',
		trustedReceiptKeys: keys as Record<string, JsonWebKey>,
		expected: {
			modelId: asNonEmptyString(expected.model_id) ?? '',
			endpoint: asNonEmptyString(expected.endpoint) ?? undefined,
			modelDigest: asNonEmptyString(expected.model_digest) ?? undefined,
			runtimeDigest: asNonEmptyString(expected.runtime_digest) ?? undefined
		}
	};

	if (
		!isHttpsUrl(config.attestationUrl) ||
		!isHttpsUrl(config.verificationUrl) ||
		!isHttpsUrl(config.receiptIssuer) ||
		!config.receiptAudience ||
		!config.expected.modelId ||
		Object.keys(config.trustedReceiptKeys).length === 0
	) {
		return null;
	}

	return config;
};

export const verifyConfidentialEndpoint = async (
	config: ConfidentialVerificationConfig,
	options: VerifyOptions = {}
): Promise<VerificationResult> => {
	try {
		const fetchImpl = options.fetchImpl ?? fetch;
		const nowMs = options.now?.() ?? Date.now();
		const nonce = toBase64Url(crypto.getRandomValues(new Uint8Array(32)));
		const attestationUrl = new URL(config.attestationUrl);
		attestationUrl.searchParams.set('nonce', nonce);

		// This request deliberately carries only a fresh nonce. It never sends a
		// chat prompt, response, API key, cookie, or account identifier.
		const response = await fetchImpl(attestationUrl, {
			method: 'GET',
			credentials: 'omit',
			cache: 'no-store',
			headers: { Accept: 'application/json' }
		});
		if (!response.ok) throw new Error(`The attestation endpoint returned ${response.status}.`);

		const payload = (await response.json()) as AttestationResponse;
		const evidence = asObject(payload.evidence);
		const receipt = asNonEmptyString(payload.verification_receipt);
		if (!evidence || !receipt) throw new Error('The attestation response is missing evidence or a receipt.');

		const { claims, keyId } = await verifyReceiptSignature(receipt, config.trustedReceiptKeys);
		const issuedAt = asEpochSeconds(claims.iat, 'iat');
		const expiresAt = asEpochSeconds(claims.exp, 'exp');
		if (expiresAt * 1000 <= nowMs) throw new Error('The verification receipt has expired.');
		if (issuedAt * 1000 > nowMs + ONE_MINUTE_MS) {
			throw new Error('The verification receipt was issued in the future.');
		}
		if (asNonEmptyString(claims.iss) !== config.receiptIssuer) {
			throw new Error('The receipt issuer does not match the configured verifier.');
		}
		if (!hasAudience(claims.aud, config.receiptAudience)) {
			throw new Error('The receipt was not issued for this application.');
		}
		if (asNonEmptyString(claims.nonce) !== nonce) {
			throw new Error('The receipt is not bound to this verification attempt.');
		}
		if (asNonEmptyString(claims.verdict) !== 'verified') {
			throw new Error('The verifier did not accept the supplied hardware evidence.');
		}
		if (asNonEmptyString(claims.model_id) !== config.expected.modelId) {
			throw new Error('The receipt model does not match the selected model.');
		}
		if (config.expected.endpoint && asNonEmptyString(claims.endpoint) !== config.expected.endpoint) {
			throw new Error('The receipt is not bound to the configured inference endpoint.');
		}
		if (
			config.expected.modelDigest &&
			asNonEmptyString(claims.model_digest) !== config.expected.modelDigest
		) {
			throw new Error('The receipt model artifact digest does not match policy.');
		}
		if (
			config.expected.runtimeDigest &&
			asNonEmptyString(claims.runtime_digest) !== config.expected.runtimeDigest
		) {
			throw new Error('The receipt runtime digest does not match policy.');
		}

		const evidenceDigest = await sha256(canonicalize(evidence));
		const receiptDigest = await sha256(receipt);
		if (asNonEmptyString(claims.evidence_sha256) !== evidenceDigest) {
			throw new Error('The receipt is not bound to the returned evidence.');
		}

		return {
			status: 'verified',
			proof: {
				issuedAt: new Date(issuedAt * 1000).toISOString(),
				expiresAt: new Date(expiresAt * 1000).toISOString(),
				modelId: config.expected.modelId,
				modelDigest: config.expected.modelDigest,
				runtimeDigest: config.expected.runtimeDigest,
				evidenceDigest,
				verificationUrl: config.verificationUrl,
				receiptKeyId: keyId,
				receiptDigest
			}
		};
	} catch (error) {
		return {
			status: 'failed',
			reason: error instanceof Error ? error.message : 'Verification failed unexpectedly.'
		};
	}
};

export const verificationEvidenceDigest = async (evidence: JsonRecord): Promise<string> =>
	sha256(canonicalize(evidence));
