import fs from 'node:fs'
import path from 'node:path'
import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const appDir = path.resolve(path.dirname(__filename), '..')
const repoRoot = path.resolve(appDir, '..', '..')
const require = createRequire(path.join(appDir, 'package.json'))

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return
  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/)
  for (const line of lines) {
    if (!line || line.trim().startsWith('#')) continue
    const separator = line.indexOf('=')
    if (separator === -1) continue
    const key = line.slice(0, separator).trim()
    if (!key || process.env[key] !== undefined) continue
    const rawValue = line.slice(separator + 1).trim().replace(/^['"]|['"]$/g, '')
    process.env[key] = rawValue
  }
}

loadEnvFile(path.join(repoRoot, '.env'))
loadEnvFile(path.join(repoRoot, '.env.local'))
loadEnvFile(path.join(appDir, '.env'))
loadEnvFile(path.join(appDir, '.env.local'))

const standaloneCandidates = [
  path.join(appDir, '.next', 'standalone', 'server.js'),
  path.join(appDir, '.next', 'standalone', 'apps', 'web', 'server.js'),
]
const standaloneServer = standaloneCandidates.find((candidate) => fs.existsSync(candidate))

if (standaloneServer) {
  await import(pathToFileURL(standaloneServer).href)
} else {
  const nextBin = require.resolve('next/dist/bin/next')
  const child = spawn(process.execPath, [nextBin, 'start', ...process.argv.slice(2)], {
    cwd: appDir,
    env: process.env,
    stdio: 'inherit',
  })
  child.on('exit', (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal)
      return
    }
    process.exit(code ?? 0)
  })
}
