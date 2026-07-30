export interface ProvenanceCarrier {
  provenance?: unknown
  demo_seed?: unknown
  config_snapshot?: { provenance?: unknown; demo_seed?: unknown } | null
}

export function isDemoData(value?: ProvenanceCarrier | null): boolean {
  return value?.provenance === 'demo'
    || value?.demo_seed === true
    || value?.config_snapshot?.provenance === 'demo'
    || value?.config_snapshot?.demo_seed === true
}
