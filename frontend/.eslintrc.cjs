/* ESLint configuration for the Finora frontend. */
module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', 'node_modules', '*.config.js', '*.config.ts', 'coverage'],
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  plugins: ['react-refresh', '@typescript-eslint'],
  rules: {
    'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    // The `_`-prefix convention marks a deliberately unused binding.
    '@typescript-eslint/no-unused-vars': [
      'error',
      { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
    ],
    // `any` is never used in this codebase; the API layer is fully typed.
    '@typescript-eslint/no-explicit-any': 'error',
    '@typescript-eslint/consistent-type-imports': [
      'error',
      { prefer: 'type-imports', fixStyle: 'inline-type-imports' },
    ],
    'no-console': ['warn', { allow: ['warn', 'error'] }],
  },
  overrides: [
    {
      files: ['**/*.test.ts', '**/*.test.tsx', 'src/test/**'],
      env: { node: true },
      rules: { '@typescript-eslint/no-explicit-any': 'off' },
    },
    {
      // Exporting a Provider alongside its `useX` consumer hook from one file
      // is the idiomatic React context pattern. Fast Refresh handles it fine;
      // the rule simply cannot tell a hook from an arbitrary constant.
      files: ['src/context/*.tsx', 'src/components/charts/Charts.tsx'],
      rules: { 'react-refresh/only-export-components': 'off' },
    },
  ],
}
