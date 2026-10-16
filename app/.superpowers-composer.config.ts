import config from "./playwright.config";
export default { ...config, webServer: undefined, testMatch: "**/composer-running.visual.ts", workers: 1 };
