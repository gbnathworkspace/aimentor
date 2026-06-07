// Single entry point for all DB access.
// Service layer imports from '@/lib/db' — never imports models or repos directly.

export { default as connectDB } from './mongoose'

// Models (for advanced use — prefer repos in service layer)
export { CoreProfileModel } from './models/core-profile.model'
export { SkillGraphNodeModel } from './models/skill-graph.model'
export { SessionModel } from './models/session.model'
export { ImmediateContextModel } from './models/immediate-context.model'
export { IngestionJobModel } from './models/ingestion-job.model'

// Repositories — use these in service layer
export { CoreProfileRepo } from './repositories/core-profile.repo'
export { SkillGraphRepo } from './repositories/skill-graph.repo'
export { SessionRepo } from './repositories/session.repo'
