export type UserRole = 'public' | 'regulator' | 'admin'

export interface User {
  id: number
  username: string
  email: string
  display_name: string
  role: UserRole
  avatar_url: string | null
  bio: string
  points: number
  stars: number
  level: number
  created_at: string
}

export interface Species {
  id: number
  common_name: string
  scientific_name: string
  english_name: string
  kingdom: string
  category: string
  protection_level: string
  rarity: number
  image_url: string
  color: string
  habitat: string
  distribution: string
  traits: string
  diet: string
  activity: string
  ecology_value: string
  threats: string
  conservation: string
  taxonomy: Record<string, string>
  facts: string[]
  source_notes: string[]
}

export interface CollectionItem {
  id: number
  species_id: number
  discovered_count: number
  knowledge_progress: number
  stars_earned: number
  favorite: boolean
  first_discovered_at: string
  last_discovered_at: string
  species: Species
}

export interface Detection {
  id: number
  track_id: number
  species_id: number | null
  category: string
  label: string
  scientific_name: string
  confidence: number
  timestamp_ms: number
  bbox: { x: number; y: number; width: number; height: number }
  color: string
  source: string
}


export interface TrackKeyframe {
  timestamp_ms: number
  bbox: { x: number; y: number; width: number; height: number }
  confidence: number
}

export interface VideoTrack {
  id: number
  detection_id: number | null
  track_id: number
  species_id: number | null
  category: string
  label: string
  scientific_name: string
  confidence: number
  color: string
  start_ms: number
  end_ms: number
  source: string
  alternatives: Array<{ name: string; scientific_name?: string; confidence?: number }>
  behavior: string
  phenomenon: string
  explanation: string
  evidence: Array<string | Record<string, unknown>>
  keyframes: TrackKeyframe[]
}

export interface VideoJob {
  id: number
  status: string
  progress: number
  mode: string
  enabled_targets: string[]
  error_message: string | null
  summary: Record<string, unknown>
  created_at: string
  completed_at: string | null
  media: {
    id: number
    filename: string
    url: string
    original_url: string
    playback_url: string
    annotated_url: string
    needs_transcode: boolean
    duration_seconds: number
    size_bytes: number
  }
}

export interface AlertEvent {
  id: number
  job_id: number | null
  event_type: string
  title: string
  severity: string
  status: string
  description: string
  timestamp_ms: number
  confidence: number
  evidence: Record<string, unknown>
  ai_advice: string
  created_at: string
}

export interface PhotoObject {
  id: number
  species_id: number | null
  discovery_id: number | null
  track_id: number
  category: string
  label: string
  common_name_zh?: string
  scientific_name: string
  confidence: number
  bbox: { x: number; y: number; width: number; height: number }
  color: string
  behavior: string
  phenomenon: string
  explanation: string
  evidence: Array<string | Record<string, unknown>>
  alternatives: Array<{ name: string; scientific_name?: string; confidence?: number }>
  speciesnet_evidence?: Record<string, unknown> | null
  bioclip_evidence?: Record<string, unknown> | null
  active_learning_evidence?: Record<string, unknown> | null
  local_prototype_evidence?: Record<string, unknown> | null
  fusion_decision?: string | null
  fusion_status?: string | null
  fusion_reason?: string | null
  bioclip_top_k?: Array<Record<string, unknown>>
  bioclip_similarity?: number | null
  bioclip_top1_margin?: number | null
  prototype_image_count?: number | null
  model_warnings?: string[]
  detections?: Array<Record<string, unknown>>
}

export interface PhotoIdentifyResult {
  job_id: number
  media_id: number
  image_url: string
  summary: string
  scene_type: string
  objects: PhotoObject[]
  warnings: string[]
  model_mode: string
  ai_correction_predictions: number
  ai_correction_enabled: boolean
  ai_correction_min_confidence?: number | null
}

export interface DiscoveryRecord {
  id: number
  job_id: number | null
  detection_id: number | null
  species_id: number | null
  record_type: 'species' | 'phenomenon' | 'behavior'
  title: string
  scientific_name: string
  category: string
  image_url: string
  confidence: number
  behavior: string
  phenomenon: string
  note: string
  stars_earned: number
  is_shared: boolean
  created_at: string
  species: Species | null
}

export interface SpeciesGuide {
  detection_id: number
  species_id?: number | null
  label: string
  scientific_name: string
  category: string
  category_zh: string
  confidence: number
  mode: string
  common_name_zh: string
  summary: string
  appearance: string
  habitat: string
  behavior: string
  similar_species: string
  observation_tips: string
  caution: string
  localized_alternatives: Array<{ name: string; scientific_name?: string; confidence?: number; common_name_zh?: string; display_name?: string }>
}
