import type { BackendSettingsData } from '@/types/api'

export const mockSettings: BackendSettingsData = {
  desired_retention: 0.9,
  learning_steps: [15],
  relearning_steps: [15],
  maximum_interval: 36500,
  default_source_scope: [],
}
