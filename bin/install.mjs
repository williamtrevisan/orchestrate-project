#!/usr/bin/env node
// Vendor the orchestrate-project skill into a repository, the way a repository
// vendors any other skill: files committed in .claude/, a content hash in
// skills-lock.json, and a refusal to overwrite a copy that has drifted.
//
// The plugin install (claude plugin install) remains the other supported shape.
// This one exists for repositories that want the skill in their own tree.

import { createHash } from 'node:crypto'
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const SKILL = 'orchestrate-project'
const SOURCE = 'williamtrevisan/orchestrate-project'
const PACKAGE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const PLUGIN_ROOT = join(PACKAGE_ROOT, 'plugins', SKILL)
const SKILL_PATH = `plugins/${SKILL}/skills/${SKILL}/SKILL.md`
const META = '.skill-meta.json'
const LOCK = 'skills-lock.json'

// Build artefacts and editor droppings are not part of the skill. Copying a
// __pycache__ would also make the content hash machine-dependent, so the same
// upstream commit would install as a different hash on a different machine.
const IGNORED = new Set(['__pycache__', '.git', '.DS_Store', 'node_modules'])
const ignored = (path) => {
  const name = path.split(sep).pop()
  return IGNORED.has(name) || name.endsWith('.pyc')
}

// What lands where. The scripts/ tree rides along with the skill because
// /orchestrate-init resolves init.py relative to the skill directory when
// CLAUDE_PLUGIN_ROOT is unset, which is exactly the vendored case.
const LAYOUT = [
  { from: join('skills', SKILL), to: join('.claude', 'skills', SKILL) },
  { from: 'scripts', to: join('.claude', 'skills', SKILL, 'scripts') },
  { from: join('commands', 'orchestrate-init.md'), to: join('.claude', 'commands', 'orchestrate-init.md') },
]

const fail = (message, code = 1) => {
  process.stderr.write(`orchestrate-project: ${message}\n`)
  process.exit(code)
}

function walk (root) {
  if (!existsSync(root) || ignored(root)) return []
  if (statSync(root).isFile()) return [root]
  return readdirSync(root, { withFileTypes: true })
    .flatMap((entry) => walk(join(root, entry.name)))
}

// One hash over every file that gets installed: each file's path relative to
// its destination, then its bytes. Path is included so a rename is a change.
function hashOf (base, entries) {
  const digest = createHash('sha256')
  // Deduped by destination key: scripts/ nests inside the skill directory, so
  // walking the installed tree reaches those files through both layout entries
  // while the payload reaches them through one. Without this the same content
  // hashes differently at the source and at the destination.
  const files = [...new Map(entries
    .flatMap(({ from, to }) => walk(join(base, from)).map((abs) => ({
      abs,
      key: join(to, relative(join(base, from), abs)).split(sep).join('/'),
    })))
    .filter(({ key }) => !key.endsWith(META))
    .map((entry) => [entry.key, entry])).values()]
    .sort((a, b) => (a.key < b.key ? -1 : 1))

  for (const { abs, key } of files) {
    digest.update(key, 'utf8')
    digest.update('\0')
    digest.update(readFileSync(abs))
  }
  return { hash: digest.digest('hex'), count: files.length }
}

const readJson = (path, fallback) => {
  if (!existsSync(path)) return fallback
  try {
    return JSON.parse(readFileSync(path, 'utf8'))
  } catch {
    return fallback
  }
}

function writeLock (root, hash) {
  const path = join(root, LOCK)
  const lock = readJson(path, { version: 1, skills: {} })
  lock.version ??= 1
  lock.skills ??= {}
  lock.skills[SKILL] = { source: SOURCE, sourceType: 'github', skillPath: SKILL_PATH, computedHash: hash }
  lock.skills = Object.fromEntries(Object.entries(lock.skills).sort(([a], [b]) => (a < b ? -1 : 1)))
  writeFileSync(path, `${JSON.stringify(lock, null, 2)}\n`)
}

function dropFromLock (root) {
  const path = join(root, LOCK)
  if (!existsSync(path)) return
  const lock = readJson(path, null)
  if (!lock?.skills?.[SKILL]) return
  delete lock.skills[SKILL]
  writeFileSync(path, `${JSON.stringify(lock, null, 2)}\n`)
}

function install (root, { force, json }) {
  if (!existsSync(PLUGIN_ROOT)) fail(`cannot find the plugin payload at ${PLUGIN_ROOT}`, 2)

  const target = join(root, '.claude', 'skills', SKILL)
  const { hash, count } = hashOf(PLUGIN_ROOT, LAYOUT)
  const installed = readJson(join(target, META), null)

  if (installed && !force) {
    // Drift is checked before staleness, and against what is on disk rather
    // than against the payload. Reversing the two hides a local edit whenever
    // upstream has not moved, which is the common case.
    const local = hashOf(root, LAYOUT.map(({ to }) => ({ from: to, to })))
    if (local.hash !== installed.contentHash) {
      fail('the installed copy has local edits. Commit or revert them, or re-run with --force to overwrite.', 3)
    }
    if (installed.contentHash === hash) {
      return report(json, { status: 'current', skill: SKILL, contentHash: hash },
        `already at this version (${hash.slice(0, 12)}) — nothing to do`)
    }
  }

  for (const { from, to } of LAYOUT) {
    const src = join(PLUGIN_ROOT, from)
    if (!existsSync(src)) fail(`missing payload entry: ${from}`, 2)
    const dest = join(root, to)
    mkdirSync(dirname(dest), { recursive: true })
    if (statSync(src).isDirectory()) rmSync(dest, { recursive: true, force: true })
    cpSync(src, dest, { recursive: true, filter: (from) => !ignored(from) })
  }

  writeFileSync(join(target, META), `${JSON.stringify({ contentHash: hash, downloadedAt: Date.now() }, null, 2)}\n`)
  writeLock(root, hash)

  return report(json, { status: 'installed', skill: SKILL, files: count, contentHash: hash },
    `installed ${count} files into .claude/ and recorded ${hash.slice(0, 12)} in ${LOCK}`)
}

function remove (root, { json }) {
  const removed = LAYOUT.filter(({ to }) => existsSync(join(root, to)))
  for (const { to } of removed) rmSync(join(root, to), { recursive: true, force: true })
  dropFromLock(root)
  return report(json, { status: removed.length ? 'removed' : 'absent', skill: SKILL },
    removed.length ? 'removed from .claude/ and from the lockfile' : 'not installed here — nothing to do')
}

function report (json, payload, human) {
  process.stdout.write(json ? `${JSON.stringify(payload, null, 2)}\n` : `orchestrate-project: ${human}\n`)
  return 0
}

const USAGE = `orchestrate-project — vendor the skill into a repository

  npx github:${SOURCE} install [--root DIR] [--force] [--json]
  npx github:${SOURCE} remove  [--root DIR] [--json]

  install   copy the skill, its references, its scripts and /orchestrate-init
            into .claude/, then record the content hash in ${LOCK}
  remove    take all of that back out

  --root    repository to install into (default: the working directory)
  --force   overwrite a copy that has local edits
  --json    machine-readable output

An install that would overwrite local edits refuses instead, so a vendored copy
never diverges silently. Re-run install to update; it is idempotent.`

function main (argv) {
  const args = argv.slice(2)
  if (!args.length || args.includes('-h') || args.includes('--help')) {
    process.stdout.write(`${USAGE}\n`)
    return
  }
  if (args.includes('-v') || args.includes('--version')) {
    process.stdout.write(`${readJson(join(PLUGIN_ROOT, '.claude-plugin', 'plugin.json'), {}).version ?? 'unknown'}\n`)
    return
  }

  const command = args[0]
  const rootFlag = args.indexOf('--root')
  const root = resolve(rootFlag === -1 ? process.cwd() : args[rootFlag + 1] ?? fail('--root needs a directory', 2))
  const options = { force: args.includes('--force') || args.includes('-f'), json: args.includes('--json') }

  if (!existsSync(root)) fail(`no such directory: ${root}`, 2)
  if (command === 'install') return install(root, options)
  if (command === 'remove') return remove(root, options)
  fail(`unknown command '${command}'. Try --help.`, 2)
}

main(process.argv)
