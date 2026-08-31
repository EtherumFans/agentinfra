import { rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const distUrl = new URL('../dist/', import.meta.url);
const distPath = fileURLToPath(distUrl);
if (!distPath.endsWith(`${process.platform === 'win32' ? '\\' : '/'}dist${process.platform === 'win32' ? '\\' : '/'}`)) {
  throw new Error('refusing to clean an unexpected build output path');
}
rmSync(distUrl, { recursive: true, force: true });
