// Bundles the server into lib/cli.mjs. The LSP libraries are bundled in, so the published package has no runtime
// dependencies, like typescript-language-server. The generated command database in data/ is read at run time.
import { build } from 'esbuild';
import { chmodSync, rmSync } from 'node:fs';

rmSync('lib', { recursive: true, force: true });

await build({
  entryPoints: ['src/cli.ts'],
  outfile: 'lib/cli.mjs',
  bundle: true,
  platform: 'node',
  format: 'esm',
  target: 'node20',
  sourcemap: false,
  minify: false,
  banner: { js: '#!/usr/bin/env node' },
  logLevel: 'info',
});

try {
  chmodSync('lib/cli.mjs', 0o755);
} catch {
  // not supported on every platform
}
