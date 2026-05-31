import type { CoreProfile, SkillGraphNode, Episode, Message, SessionMode } from '@/lib/schemas'

export type PromptVersion = `v${number}`

export interface PromptBuilderInput {
  coreProfile: CoreProfile
  skillGraphNodes: SkillGraphNode[]
  episodes: Episode[]
  conversationWindow: Message[]
  currentTopic?: string
}

export type PromptBuilder = (input: PromptBuilderInput) => string

export interface PromptEntry {
  version: PromptVersion
  mode: SessionMode
  build: PromptBuilder
}
