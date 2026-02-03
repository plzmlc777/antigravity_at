import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { readFileSync } from 'fs'
import { execSync } from 'child_process'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
    // Load env file based on `mode` in the current working directory.
    const env = loadEnv(mode, process.cwd(), '')

    // 1. Read package.json for version
    const pkg = JSON.parse(readFileSync(path.resolve(__dirname, 'package.json'), 'utf-8'));

    // 2. Get Git Hash
    let commitHash = 'unknown';
    try {
        commitHash = execSync('git rev-parse --short HEAD').toString().trim();
    } catch (e) {
        console.warn('Failed to get git hash', e);
    }

    return {
        plugins: [react()],
        define: {
            '__APP_VERSION__': JSON.stringify(pkg.version),
            '__COMMIT_HASH__': JSON.stringify(commitHash),
        },
        resolve: {
            alias: {
                "@": path.resolve(__dirname, "./src"),
            },
        },
        server: {
            port: parseInt(env.FRONTEND_PORT) || 5173,
            strictPort: true,
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
