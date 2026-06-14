import type { CoreProfile, SkillGraphNode, Episode, Message } from '@/lib/schemas'
import type { PromptBuilderInput } from '@/lib/prompts/types'

// ─── Skipped Onboarding Addendum ──────────────────────────────────────────────
// Appended to the system prompt when the user has not completed onboarding.
// Instructs the LLM to keep all responses general and topic-focused.

export const SKIPPED_ONBOARDING_ADDENDUM = `
IMPORTANT: This user has NOT completed onboarding. No specific goal, skill data, 
or study plan is available. You must:
- Keep all advice general and topic-focused
- Never reference specific deadlines, skill gaps, or personalized study plans
- Respond helpfully to whatever they ask
- If they ask about personalized features, suggest completing their profile setup
`

// ─── Constants ────────────────────────────────────────────────────────────────

/** Maximum number of recent conversation turns to include in degraded context */
export const CONVERSATION_WINDOW_SIZE = 6

// ─── Types ────────────────────────────────────────────────────────────────────

export interface AssembleContextInput {
  coreProfile: CoreProfile | null
  skillGraphNodes: SkillGraphNode[]
  episodes: Episode[]
  conversationWindow: Message[]
  currentTopic?: string
}

export interface AssembledContextResult {
  /** The prompt builder input, with profile fields cleaned and layers omitted as needed */
  promptInput: PromptBuilderInput
  /** Whether the skipped-onboarding addendum should be appended to the system prompt */
  addendum: string | null
  /** Whether skill graph was included (false when profile is skipped or empty) */
  skillGraphIncluded: boolean
  /** Whether episodic memory was included (false when profile is skipped) */
  episodicMemoryIncluded: boolean
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Builds a safe CoreProfile for prompt injection.
 * Omits any field that is null, undefined, or empty string.
 * Returns a profile object where missing fields are replaced with empty strings
 * so downstream prompt builders never throw on property access.
 */
function buildSafeProfile(profile: CoreProfile | null): CoreProfile {
  if (!profile) {
    return {
      userId: '',
      goal: '',
      deadline: null,
      overall_level: '',
      daily_availability: '',
      email: '',
      profile_status: 'skipped',
    }
  }

  return {
    userId: profile.userId ?? '',
    goal: profile.goal ?? '',
    deadline: profile.deadline ?? null,
    overall_level: profile.overall_level ?? '',
    daily_availability: profile.daily_availability ?? '',
    email: profile.email ?? '',
    profile_status: profile.profile_status ?? 'complete',
  }
}

/**
 * Checks if a profile is in "skipped" state.
 */
function isSkippedProfile(profile: CoreProfile | null): boolean {
  return profile?.profile_status === 'skipped'
}

// ─── Main Assembly Function ───────────────────────────────────────────────────

/**
 * Assembles LLM context with graceful degradation for skipped/incomplete profiles.
 *
 * Behavior:
 * - When profile_status === "skipped":
 *   - Appends SKIPPED_ONBOARDING_ADDENDUM to system prompt
 *   - Omits Skill Graph layer entirely
 *   - Omits Episodic Memory layer entirely
 *   - Includes conversation window (last 6 turns)
 *
 * - When any Core Profile field is missing/null:
 *   - Omits that field from assembled context without erroring
 *
 * - When all profile fields are missing:
 *   - Assembles using only system prompt + addendum + conversation window
 *
 * - NEVER throws an error due to missing profile data
 */
export function assembleContext(input: AssembleContextInput): AssembledContextResult {
  const { coreProfile, skillGraphNodes, episodes, conversationWindow, currentTopic } = input

  const safeProfile = buildSafeProfile(coreProfile)
  const skipped = isSkippedProfile(coreProfile) || !coreProfile

  // For skipped profiles: omit skill graph and episodic memory entirely
  const includedSkillGraph = skipped ? [] : skillGraphNodes
  const includedEpisodes = skipped ? [] : episodes

  // Trim conversation window to last N turns
  const trimmedConversation = conversationWindow.slice(-CONVERSATION_WINDOW_SIZE)

  const promptInput: PromptBuilderInput = {
    coreProfile: safeProfile,
    skillGraphNodes: includedSkillGraph,
    episodes: includedEpisodes,
    conversationWindow: trimmedConversation,
    currentTopic,
  }

  return {
    promptInput,
    addendum: skipped ? SKIPPED_ONBOARDING_ADDENDUM : null,
    skillGraphIncluded: !skipped && skillGraphNodes.length > 0,
    episodicMemoryIncluded: !skipped,
  }
}
