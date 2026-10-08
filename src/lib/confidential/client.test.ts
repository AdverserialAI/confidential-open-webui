import { describe, expect, it } from 'vitest';

import { isConfidentialModel } from './client';

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
