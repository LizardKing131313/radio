import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import globals from "globals";
import jsxA11y from "eslint-plugin-jsx-a11y";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

const typeCheckedConfigs = [
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked
].map((config) => ({
  ...config,
  files: ["**/*.{ts,tsx}"]
}));

const tsxConfig = (config) => ({
  ...config,
  files: ["**/*.tsx"],
  settings: {
    ...config.settings,
    react: {
      version: "18.2",
      pragma: "h",
      fragment: "Fragment"
    }
  }
});

export default tseslint.config(
  {
    ignores: ["dist/**", "node_modules/**"]
  },
  {
    ...js.configs.recommended,
    files: ["**/*.{js,mjs}"],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node
      }
    },
    rules: {
      ...js.configs.recommended.rules,
      eqeqeq: ["error", "always"],
      "no-console": ["error", {allow: ["warn", "error"]}]
    }
  },
  ...typeCheckedConfigs,
  tsxConfig(react.configs.flat.recommended),
  tsxConfig(react.configs.flat["jsx-runtime"]),
  tsxConfig(reactHooks.configs.flat["recommended-latest"]),
  tsxConfig(jsxA11y.flatConfigs.strict),
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.es2022
      },
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname
      }
    },
    rules: {
      "@typescript-eslint/consistent-type-imports": "error",
      "@typescript-eslint/no-confusing-void-expression": ["error", {ignoreArrowShorthand: true}],
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-misused-promises": "error",
      "@typescript-eslint/no-unnecessary-condition": "error",
      "@typescript-eslint/restrict-template-expressions": [
        "error",
        {allowBoolean: true, allowNever: true, allowNullish: true, allowNumber: false}
      ],
      eqeqeq: ["error", "always"],
      "jsx-a11y/media-has-caption": "off",
      "no-console": ["error", {allow: ["warn", "error"]}]
    }
  },
  {
    files: ["**/*.test.ts", "vite.config.ts"],
    languageOptions: {
      globals: globals.node
    }
  },
  prettier
);
