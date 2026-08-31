import { copyFileSync, mkdirSync, readdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const compiler = resolve(packageRoot, 'node_modules', 'typescript', 'bin', 'tsc');
const sourceDir = resolve(packageRoot, 'src');
const outputDir = resolve(packageRoot, 'dist');

execFileSync(process.execPath, [compiler], {
  cwd: packageRoot,
  stdio: 'inherit',
});

mkdirSync(outputDir, { recursive: true });
for (const filename of readdirSync(sourceDir)) {
  if (filename.endsWith('.css')) {
    copyFileSync(resolve(sourceDir, filename), resolve(outputDir, filename));
  }
}
