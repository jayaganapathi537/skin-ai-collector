import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist/**', 'functions/lib/**', 'node_modules/**'] },
  ...tseslint.configs.recommended,
)
