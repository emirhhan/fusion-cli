import {
  readdirSync,
  readFileSync,
  lstatSync,
  mkdirSync,
  writeFileSync,
} from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { zipSync } from 'fflate';
import process from 'node:process';
import { assertRuntime, projectRoot } from './kits-start.mjs';

const roots = new Set([
  'src',
  'public',
  'tests',
  'scripts',
  'docs',
  'deployment',
  'handoff',
  'dist',
  '.github',
]);
const rootFiles = new Set([
  'package.json',
  'package-lock.json',
  'README.md',
  'LICENSE',
  'LICENSE.fusion',
  'SECURITY.md',
  'CONTRIBUTING.md',
  'Dockerfile',
  '.dockerignore',
  '.gitignore',
  '.env.example',
  'index.html',
  'tsconfig.json',
  'tsconfig.server.json',
  'vite.config.ts',
  'eslint.config.js',
  'start.command',
  'start.ps1',
]);
function excluded(path) {
  return (
    path
      .split('/')
      .some(
        (part) =>
          [
            '.git',
            'node_modules',
            'data',
            '.DS_Store',
            '__pycache__',
            '.voice-lab',
          ].includes(part) ||
          (part.startsWith('.env') && part !== '.env.example'),
      ) ||
    /\.sqlite(?:-(?:wal|shm))?$/.test(path) ||
    /\.py[co]$/.test(path)
  );
}
export function collectFiles(root) {
  const files = [];
  function walk(relative) {
    if (excluded(relative)) return;
    const stat = lstatSync(join(root, relative));
    if (stat.isSymbolicLink())
      throw new Error(`Pakete sembolik bağlantı alınmaz: ${relative}`);
    if (stat.isDirectory()) {
      for (const entry of readdirSync(join(root, relative)).sort())
        walk(`${relative}/${entry}`);
    } else if (stat.isFile()) files.push(relative);
  }
  for (const entry of readdirSync(root).sort()) {
    if (
      roots.has(entry) ||
      rootFiles.has(entry) ||
      /^compose(?:\.[a-z-]+)*\.yml$/.test(entry)
    )
      walk(entry);
  }
  return files.sort();
}
export function buildPackage(
  root = projectRoot,
  outputDir = resolve(projectRoot, 'release'),
) {
  const files = collectFiles(root);
  const pkg = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
  const upstream = JSON.parse(
    readFileSync(join(root, 'handoff/upstream.json'), 'utf8'),
  );
  const manifest = {
    product: 'Fusion Kits',
    version: pkg.version,
    upstream,
    files: [],
  };
  const entries = {};
  const mtime = new Date('2026-10-04T00:00:00Z');
  for (const path of files) {
    const bytes = readFileSync(join(root, path));
    const sha256 = createHash('sha256').update(bytes).digest('hex');
    manifest.files.push({ path, bytes: bytes.length, sha256 });
    entries[`fusion-kits/${path}`] = [
      bytes,
      {
        mtime,
        os: 3,
        attrs: (path === 'start.command' ? 0o100755 : 0o100644) << 16,
      },
    ];
  }
  const manifestBytes = Buffer.from(JSON.stringify(manifest, null, 2) + '\n');
  entries['fusion-kits/MANIFEST.json'] = [manifestBytes, { mtime }];
  const zip = zipSync(entries, { level: 6, mtime });
  mkdirSync(outputDir, { recursive: true });
  const zipPath = join(outputDir, 'fusion-kits.zip');
  const manifestPath = join(outputDir, 'MANIFEST.json');
  writeFileSync(zipPath, zip);
  writeFileSync(manifestPath, manifestBytes);
  const sha256 = createHash('sha256').update(zip).digest('hex');
  writeFileSync(
    join(outputDir, 'fusion-kits.zip.sha256'),
    `${sha256}  fusion-kits.zip\n`,
  );
  return {
    zipPath,
    manifestPath,
    sha256,
    bytes: zip.length,
    files: files.length,
  };
}
if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href
) {
  try {
    assertRuntime();
    console.log(JSON.stringify(buildPackage(), null, 2));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
