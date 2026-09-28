import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { platform } from 'node:os'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../', import.meta.url))
const backend = `${root}backend`
const python = platform() === 'win32' ? `${backend}/.venv/Scripts/python.exe` : `${backend}/.venv/bin/python`
if (!existsSync(python)) throw new Error(`Backend virtual environment was not found: ${python}`)

const commands = [
  ['backend', python, ['-m', 'uvicorn', 'app.main:app', '--reload', '--host', '0.0.0.0', '--port', '8000'], backend],
  ['frontend', platform() === 'win32' ? `${root}frontend/node_modules/.bin/vite.cmd` : `${root}frontend/node_modules/.bin/vite`, [], `${root}frontend`],
]
const backendOnly = process.argv.includes('--backend-only')
const frontendOnly = process.argv.includes('--frontend-only')
const children = []
let stopping = false
function start([name, command, args, cwd]) {
  const child = spawn(command, args, { cwd, stdio: ['inherit', 'pipe', 'pipe'], shell: false })
  for (const [stream, output] of [[child.stdout, process.stdout], [child.stderr, process.stderr]]) {
    stream.on('data', data => output.write(`[${name}] ${data}`))
  }
  child.on('exit', code => {
    if (!stopping && code !== 0) { console.error(`[${name}] exited with code ${code}`); stop(code || 1) }
  })
  children.push(child)
}
function stop(exitCode = 0) {
  if (stopping) return
  stopping = true
  for (const child of children) child.kill('SIGTERM')
  setTimeout(() => process.exit(exitCode), 500)
}
process.on('SIGINT', () => stop())
process.on('SIGTERM', () => stop())
if (!frontendOnly) start(commands[0])
if (!backendOnly) start(commands[1])
