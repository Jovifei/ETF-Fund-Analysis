export function withGeneration(path: string, generation?: string | number | null): string {
  return generation == null ? path : `${path}${path.includes('?') ? '&' : '?'}generation=${encodeURIComponent(generation)}`
}
