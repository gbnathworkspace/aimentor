import type { SessionMode } from '@/lib/schemas'
import type { PromptBuilder, PromptVersion } from './types'
import { build as planningV1 } from './planning.prompt'
import { build as topicV1 } from './topic.prompt'
import { build as doubtV1 } from './doubt.prompt'
import { build as evaluationV1 } from './evaluation.prompt'

type PromptKey = `${SessionMode}:${PromptVersion}`

const registry = new Map<PromptKey, PromptBuilder>([
  ['planning:v1', planningV1],
  ['topic:v1', topicV1],
  ['doubt:v1', doubtV1],
  ['evaluation:v1', evaluationV1],
])

const CURRENT_VERSIONS: Record<SessionMode, PromptVersion> = {
  planning: 'v1',
  topic: 'v1',
  doubt: 'v1',
  evaluation: 'v1',
}

export class PromptStore {
  get(mode: SessionMode, version?: PromptVersion): PromptBuilder {
    const v = version ?? CURRENT_VERSIONS[mode]
    const key: PromptKey = `${mode}:${v}`
    const builder = registry.get(key)
    if (!builder) throw new Error(`No prompt registered for ${key}`)
    return builder
  }

  currentVersion(mode: SessionMode): PromptVersion {
    return CURRENT_VERSIONS[mode]
  }
}

export const promptStore = new PromptStore()
