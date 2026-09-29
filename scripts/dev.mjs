import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { platform } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../', import.meta.url))
const backend = join(root, 'backend')
const frontend = join(root, 'frontend')
const isWindows = platform() === 'win32'
const python = isWindows ? join(backend, '.venv', 'Scripts', 'python.exe') : join(backend, '.venv', 'bin', 'python')
if (!existsSync(python)) throw new Error(`Backend virtual environment was not found: ${python}`)

const commands = [
  ['backend', python, ['-m', 'uvicorn', 'app.main:app', '--reload', '--host', '0.0.0.0', '--port', '8000'], backend],
  // Windows cannot CreateProcess a .cmd file with shell:false. Run the unchanged
  // frontend command through cmd.exe explicitly, while Python remains direct.
  ['frontend', isWindows ? (process.env.ComSpec || 'cmd.exe') : 'npm', isWindows ? ['/d', '/s', '/c', 'npm.cmd run dev'] : ['run', 'dev'], frontend],
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
  child.on('error', error => {
    if (!stopping) { console.error(`[${name}] failed to start: ${error.message}`); stop(1) }
  })
  children.push(child)
}
function stop(exitCode = 0) {
  if (stopping) return
  stopping = true
  for (const child of children) {
    if (!child.pid) continue
    if (isWindows) {
      // /T terminates npm/Vite or Uvicorn's reload child tree too, preventing orphans.
      spawn('taskkill.exe', ['/pid', String(child.pid), '/t', '/f'], { stdio: 'ignore', shell: false })
    } else child.kill('SIGTERM')
  }
  setTimeout(() => process.exit(exitCode), 800)
}
process.on('SIGINT', () => stop())
process.on('SIGTERM', () => stop())
if (!frontendOnly) start(commands[0])
if (!backendOnly) start(commands[1])
