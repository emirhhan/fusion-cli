import { startKits } from './start-kits.js';
import { reportChannelFailure, safeFailure } from './slack-channel.js';
const running = await startKits();
const shutdown = () => {
  void running.close().then(
    () => process.exit(0),
    (error) => {
      reportChannelFailure('Shutdown failed', [safeFailure(error)]);
      process.exit(1);
    },
  );
};
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
