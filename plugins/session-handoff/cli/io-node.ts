/** `Io` over Node's disk and git, for the hosts that run the plugin as a process or in Bun (spec 001 · 03 §2). */
import { execFile } from 'node:child_process'
import { promises as fs } from 'node:fs'
import path from 'node:path'

import type { Io } from '../hooks/store'

const GIT_TIMEOUT_MS = 10_000

export const nodeIo: Io = {
  read: file => fs.readFile(file, 'utf8').catch(() => null),
  // Temp file and rename: a hook killed mid-write never leaves half a PROGRESS.md or state file.
  write: async (file, text) => {
    await fs.mkdir(path.dirname(file), { recursive: true })
    const tmp = `${file}.${process.pid}.${Date.now()}.tmp`
    await fs.writeFile(tmp, text, 'utf8')
    await fs.rename(tmp, file)
  },
  list: async dir => {
    const entries = await fs.readdir(dir, { withFileTypes: true })
    return Promise.all(
      entries.map(async e => ({
        name: e.name,
        kind: e.isDirectory() ? 'dir' : 'file',
        mtimeMs: (await fs.stat(path.join(dir, e.name)).catch(() => null))?.mtimeMs,
      })),
    )
  },
  git: (cwd, args) =>
    new Promise(resolve => {
      execFile('git', args, { cwd, timeout: GIT_TIMEOUT_MS, windowsHide: true }, (error, stdout) =>
        resolve(error ? '' : String(stdout).trim()),
      )
    }),
}
