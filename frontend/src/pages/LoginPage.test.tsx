// @vitest-environment jsdom
import { expect, test, vi } from 'vitest';
vi.mock('../store', () => ({useAuthStore: vi.fn(), useToastStore: vi.fn()}));
import { authenticationError } from './LoginPage';

test('validation errors become readable text without exposing submitted values', () => {
  const message = authenticationError({response:{data:{detail:[
    {loc:['body','email'],msg:'invalid email',input:'private@example.test'},
  ]}}}, '注册失败');
  expect(message).toContain('邮箱');
  expect(message).not.toContain('private@example.test');
});

test('structured and ordinary auth failures remain readable', () => {
  expect(authenticationError({response:{data:{detail:{message:'账户已停用'}}}}, '失败')).toBe('账户已停用');
  expect(authenticationError({response:{data:{detail:'登录失败'}}}, '失败')).toBe('登录失败');
  expect(authenticationError(new Error('offline'), '网络失败')).toBe('网络失败');
});

test('service faults are distinguished from account rejection without leaking server details', () => {
  expect(authenticationError({response:{status:503,data:{detail:'postgres://secret'}}},'登录失败')).toContain('服务暂时不可用');
  expect(authenticationError({request:{},code:'ERR_NETWORK'},'登录失败')).toContain('无法连接服务');
  expect(authenticationError({code:'ECONNABORTED'},'登录失败')).toContain('连接超时');
});
