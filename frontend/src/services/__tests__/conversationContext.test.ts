// @vitest-environment jsdom
import { beforeEach, expect, test } from 'vitest';
import { contextKey, readContext, saveContext } from '../conversationContext';
beforeEach(() => sessionStorage.clear());
test('context references resume only within actor, organization and agent', () => {
  const key = contextKey('alice', 'org-a', 'agent-a');
  saveContext(key, 'context-1');
  expect(readContext(key)).toBe('context-1');
  expect(readContext(contextKey('alice', 'org-b', 'agent-a'))).toBe('');
  expect(readContext(contextKey('bob', 'org-a', 'agent-a'))).toBe('');
  expect(readContext(contextKey('alice', 'org-a', 'agent-b'))).toBe('');
  saveContext(key, '');
  expect(readContext(key)).toBe('');
});
