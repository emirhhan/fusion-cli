import config from "./playwright.config";
export default { ...config, webServer: undefined, testMatch: "**/image-review.visual.ts", workers: 1 };
