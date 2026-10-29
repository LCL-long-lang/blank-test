/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 'true' 时使用 src/mocks，不访问后端 */
  readonly VITE_USE_MOCK?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
