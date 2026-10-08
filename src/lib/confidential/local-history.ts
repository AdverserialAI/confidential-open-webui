/**
 * Browser-owned storage for confidential chat transcripts.
 *
 * This module intentionally has no HTTP dependency. Records live in IndexedDB
 * under the current browser origin and are keyed by the signed-in Open WebUI
 * user ID plus an opaque local conversation ID. The server never receives this
 * data through the confidential route.
 */

export type LocalConfidentialHistory = {
	messages: Record<string, any>;
	currentId: string | null;
};

export type LocalConfidentialConversation = {
	key: string;
	ownerId: string;
	conversationId: string;
	modelId: string;
	createdAt: number;
	updatedAt: number;
	history: LocalConfidentialHistory;
};

const DATABASE_NAME = 'adverserial-confidential-chat';
const DATABASE_VERSION = 1;
const STORE_NAME = 'conversations';

const available = () => typeof window !== 'undefined' && typeof indexedDB !== 'undefined';
const recordKey = (ownerId: string, conversationId: string) => `${ownerId}:${conversationId}`;

const openDatabase = (): Promise<IDBDatabase> =>
	new Promise((resolve, reject) => {
		if (!available()) {
			reject(new Error('Browser local storage is unavailable.'));
			return;
		}
		const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
		request.onerror = () => reject(request.error ?? new Error('Could not open browser local storage.'));
		request.onupgradeneeded = () => {
			if (!request.result.objectStoreNames.contains(STORE_NAME)) {
				request.result.createObjectStore(STORE_NAME, { keyPath: 'key' });
			}
		};
		request.onsuccess = () => resolve(request.result);
	});

const copyHistory = (history: LocalConfidentialHistory): LocalConfidentialHistory => {
	const messages: Record<string, any> = {};
	for (const [id, message] of Object.entries(history.messages ?? {})) {
		if (!message || typeof message !== 'object') continue;
		// Attachments, tool state, and arbitrary component objects are purposely
		// excluded. Confidential transport currently supports text-only messages.
		messages[id] = {
			id,
			parentId: typeof message.parentId === 'string' ? message.parentId : null,
			childrenIds: Array.isArray(message.childrenIds)
				? message.childrenIds.filter((child: unknown) => typeof child === 'string')
				: [],
			role: typeof message.role === 'string' ? message.role : 'user',
			content: typeof message.content === 'string' ? message.content : '',
			timestamp: typeof message.timestamp === 'number' ? message.timestamp : Date.now() / 1000,
			done: message.done === true,
			model: typeof message.model === 'string' ? message.model : undefined,
			modelName: typeof message.modelName === 'string' ? message.modelName : undefined,
			modelIdx: typeof message.modelIdx === 'number' ? message.modelIdx : undefined,
			info: message.info?.confidential === true ? { confidential: true, stored: 'browser' } : undefined
		};
	}
	return {
		messages,
		currentId: typeof history.currentId === 'string' && messages[history.currentId] ? history.currentId : null
	};
};

export const saveLocalConfidentialConversation = async ({
	ownerId,
	conversationId,
	modelId,
	history
}: Omit<LocalConfidentialConversation, 'key' | 'createdAt' | 'updatedAt'>): Promise<void> => {
	const database = await openDatabase();
	try {
		const now = Date.now();
		const transaction = database.transaction(STORE_NAME, 'readwrite');
		const store = transaction.objectStore(STORE_NAME);
		const key = recordKey(ownerId, conversationId);
		const current = await new Promise<LocalConfidentialConversation | undefined>((resolve, reject) => {
			const request = store.get(key);
			request.onerror = () => reject(request.error);
			request.onsuccess = () => resolve(request.result as LocalConfidentialConversation | undefined);
		});
		store.put({
			key,
			ownerId,
			conversationId,
			modelId,
			createdAt: current?.createdAt ?? now,
			updatedAt: now,
			history: copyHistory(history)
		} satisfies LocalConfidentialConversation);
		await new Promise<void>((resolve, reject) => {
			transaction.oncomplete = () => resolve();
			transaction.onerror = () => reject(transaction.error);
			transaction.onabort = () => reject(transaction.error);
		});
	} finally {
		database.close();
	}
};

export const loadLocalConfidentialConversation = async (
	ownerId: string,
	conversationId: string
): Promise<LocalConfidentialConversation | null> => {
	const database = await openDatabase();
	try {
		const transaction = database.transaction(STORE_NAME, 'readonly');
		const record = await new Promise<LocalConfidentialConversation | undefined>((resolve, reject) => {
			const request = transaction.objectStore(STORE_NAME).get(recordKey(ownerId, conversationId));
			request.onerror = () => reject(request.error);
			request.onsuccess = () => resolve(request.result as LocalConfidentialConversation | undefined);
		});
		if (!record || record.ownerId !== ownerId || record.conversationId !== conversationId) return null;
		return { ...record, history: copyHistory(record.history) };
	} finally {
		database.close();
	}
};

export const deleteLocalConfidentialConversation = async (ownerId: string, conversationId: string) => {
	const database = await openDatabase();
	try {
		const transaction = database.transaction(STORE_NAME, 'readwrite');
		transaction.objectStore(STORE_NAME).delete(recordKey(ownerId, conversationId));
		await new Promise<void>((resolve, reject) => {
			transaction.oncomplete = () => resolve();
			transaction.onerror = () => reject(transaction.error);
			transaction.onabort = () => reject(transaction.error);
		});
	} finally {
		database.close();
	}
};
