import process from 'node:process';
// Windows dahil tüm platformlarda shell'e özel env atamasından kaçınılır.
process.env.NODE_ENV = 'development';
await import('../src/server/index.ts');
