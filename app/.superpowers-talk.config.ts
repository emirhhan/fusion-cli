import config from "./playwright.config";
export default { ...config, webServer: undefined, testMatch: "**/talk-pet.visual.ts", workers: 1 };
