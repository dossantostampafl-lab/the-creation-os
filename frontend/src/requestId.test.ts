import { afterEach, expect, it, vi } from 'vitest';
import { newRequestId } from './requestId';
afterEach(()=>vi.unstubAllGlobals());
it('uses Web Crypto to generate version4 IDs when randomUUID is unavailable',()=>{
  const fill = vi.fn((bytes: Uint8Array)=>{bytes.fill(255);return bytes;});
  vi.stubGlobal('crypto',{getRandomValues:fill});
  expect(newRequestId()).toBe('ffffffff-ffff-4fff-bfff-ffffffffffff');
  expect(fill).toHaveBeenCalledOnce();
});
