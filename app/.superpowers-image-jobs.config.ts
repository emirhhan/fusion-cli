import config from "./playwright.config";
export default { ...config, webServer: undefined, testMatch: "**/image-jobs.visual.ts", workers: 1 };
