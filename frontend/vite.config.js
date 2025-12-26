import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
    // Load env file based on `mode` in the current working directory.
    // Set the third parameter to '' to load all env regardless of the `VITE_` prefix.
    const env = loadEnv(mode, process.cwd(), '')

    return {
        plugins: [react()],
        resolve: {
            alias: {
                "@": path.resolve(__dirname, "./src"),
            },
        },
        server: {
            port: parseInt(env.FRONTEND_PORT) || 5173,
            strictPort: true, // Fail if port is busy
            proxy: {
                '/api': {
                    target: `http://127.0.0.1:${env.BACKEND_PORT || 8001}`,
                    changeOrigin: true,
                    secure: false,
                }
            }
        }
    }
})
