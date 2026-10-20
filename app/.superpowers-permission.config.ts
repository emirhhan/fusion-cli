import config from "./playwright.config";
export default { ...config, webServer: undefined, testMatch: "**/permission-fit.visual.ts", workers: 1 };
