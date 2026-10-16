import config from "./playwright.config";
export default { ...config, webServer: undefined, testMatch: "**/onboarding-flow.visual.ts", workers: 1 };
