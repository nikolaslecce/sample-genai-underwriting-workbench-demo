import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'url'
import path from 'path'
import fs from 'fs-extra'

const __dirname = path.dirname(fileURLToPath(import.meta.url))


// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
})
