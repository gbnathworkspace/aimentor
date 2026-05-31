import fs from 'fs'
import path from 'path'
import { SessionMode } from '@/lib/schemas'

// ─── PromptLoader ─────────────────────────────────────────────────────────────
// Reads versioned prompt files from /prompts/ at runtime.
// SessionService calls this — never hardcodes prompt strings directly.
//
// File naming: prompts/session/{mode}.v{n}.md
// To change a prompt: add a new version file, bump ACTIVE_VERSIONS below.
// Old versions stay in place for rollback.

const PROMPTS_DIR = path.join(process.cwd(), 'prompts')

// ── Bump these to activate a new prompt version ──────────────────────────────
const ACTIVE_VERSIONS: Record<SessionMode, number> = {
  topic:      1,
  doubt:      1,
  planning:   1,
  evaluation: 1,
}

const EVAL_VERSIONS: Record<'recall' | 'application' | 'depth', number> = {
  recall:      1,
  application: 1,
  depth:       1,
}

// Cache loaded prompts in memory — files don't change at runtime
const cache = new Map<string, string>()

function loadFile(filePath: string): string {
  if (cache.has(filePath)) return cache.get(filePath)!

  if (!fs.existsSync(filePath)) {
    throw new Error(`Prompt file not found: ${filePath}`)
  }

  const content = fs.readFileSync(filePath, 'utf-8')
  cache.set(filePath, content)
  return content
}

// ─── Public API ───────────────────────────────────────────────────────────────

export const PromptLoader = {

  // Load a session mode prompt and interpolate context variables
  loadSessionPrompt(mode: SessionMode, vars: Record<string, string>): string {
    const version = ACTIVE_VERSIONS[mode]
    const filePath = path.join(PROMPTS_DIR, 'session', `${mode}.v${version}.md`)
    const template = loadFile(filePath)
    return interpolate(template, vars)
  },

  // Load an evaluation question-level guideline
  loadEvalPrompt(level: 'recall' | 'application' | 'depth', vars: Record<string, string>): string {
    const version = EVAL_VERSIONS[level]
    const filePath = path.join(PROMPTS_DIR, 'evaluation', `${level}.v${version}.md`)
    const template = loadFile(filePath)
    return interpolate(template, vars)
  },

  // Returns which version is active — useful for logging in AssembledContext.meta
  activeVersion(mode: SessionMode): string {
    return `${mode}.v${ACTIVE_VERSIONS[mode]}`
  },

  // Clear cache — useful in tests or if prompts are hot-reloaded in dev
  clearCache(): void {
    cache.clear()
  },
}

// ─── Template interpolation ───────────────────────────────────────────────────
// Replaces {{variable_name}} placeholders with values from vars.
// Throws if a placeholder has no matching value — fail loud, not silently empty.

function interpolate(template: string, vars: Record<string, string>): string {
  return template.replace(/\{\{(\w+)\}\}/g, (match, key) => {
    if (!(key in vars)) {
      throw new Error(`Prompt template variable missing: {{${key}}}`)
    }
    return vars[key]
  })
}
