// URL-scheme gate for any window.open we do on data that can come from a
// chat payload (citations, file/link attachments). An attacker can store a
// `javascript:` URI in a shared chat; without this check, clicking the
// citation or attachment executes JS in the viewer's browser — including
// an admin's — and steals localStorage.token (R10 / ADV5-001).

const ALLOWED_SCHEMES = new Set(['https:', 'http:']); // be strict: only web URLs open in new tabs

export function safeOpenUrl(url: string, target: '_blank' | '_self' = '_blank'): boolean {
	// Relative paths (own origin) are always safe
	if (url.startsWith('/')) {
		window.open(url, target);
		return true;
	}
	try {
		const scheme = new URL(url).protocol;
		if (!ALLOWED_SCHEMES.has(scheme)) {
			console.warn(`blocked unsafe window.open for scheme [${scheme}]`);
			return false;
		}
	} catch {
		console.warn(`blocked unparsable window.open for url [${url}]`);
		return false;
	}
	window.open(url, target);
	return true;
}
