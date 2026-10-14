import tseslint from "typescript-eslint";
import hooks from "eslint-plugin-react-hooks";

// Hook sırası tüm kaynakta zorunlu. Bağımlılık kapısı P3'ün sahibi olduğu async yolları kapsar.
const ownedAsync = [
  "src/App.tsx", "src/SessionApplication.tsx", "src/sessions/useSessions.ts",
  "src/onboarding/*.tsx", "src/settings/Settings.tsx", "src/imagecreate/*.tsx", "src/imagecreate/useImageDiscovery.ts",
  "src/screens/ModelPicker.tsx", "src/screens/useModelCatalog.ts", "src/screens/useActiveModel.ts", "src/settings/sections/Models.tsx",
  "src/screens/Composer.tsx", "src/screens/Conversation.tsx", "src/control/ControlPanel.tsx", "src/control/ProviderList.tsx",
 ];
export default [
  { ignores: ["**/*.test.*", "dist/**", "src-tauri/**"] },
  { files: ["src/**/*.{ts,tsx}"], languageOptions: { parser: tseslint.parser }, plugins: { "react-hooks": hooks }, rules: { "react-hooks/rules-of-hooks": "error" } },
  // Görünür küresel tarama: P16'da P3 dışındaki bağımlılıklar da strict kapıya taşınır.
  ...(process.env.FUSION_HOOKS_GLOBAL === "1" ? [{ files: ["src/**/*.{ts,tsx}"], rules: { "react-hooks/exhaustive-deps": "warn" } }] : []),
  { files: ownedAsync, rules: { "react-hooks/exhaustive-deps": "error" } },
];
