import { createHash } from 'node:crypto';
import { lstatSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
const [source, version] = process.argv.slice(2);
if (!source || !version || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/.test(version)) throw new Error('Usage: node create-build-manifest.mjs <staging-directory> <simple-version>');
const directory = resolve(source);
const declarations = [
  { id: 'android-debug', title: 'Android Debug', filename: 'creation-debug.apk', type: 'apk', variant: 'debug' },
  { id: 'android-release', title: 'Android Release sem assinatura', filename: 'creation-release-unsigned.apk', type: 'apk', variant: 'release_unsigned' },
  { id: 'android-bundle', title: 'Android Bundle sem assinatura', filename: 'creation-release.aab', type: 'aab', variant: 'release_unsigned' },
];
const files = declarations.map(entry => {
  const filename = join(directory, entry.filename);
  const stat = lstatSync(filename);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size <= 0) throw new Error(`Invalid artifact: ${entry.filename}`);
  return { ...entry, size_bytes: stat.size, sha256: createHash('sha256').update(readFileSync(filename)).digest('hex') };
});
writeFileSync(join(directory, 'manifest.json'), JSON.stringify({ schema_version: 1, version, files }, null, 2) + '\n');
console.log(`Manifest ${version}: ${files.length} verified artifacts`);
