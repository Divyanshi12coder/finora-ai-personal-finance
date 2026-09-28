/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the Finora API. Defaults to "/api" (dev proxy). */
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
