/**
 * Resolve item / content icon URLs (§0.0.4).
 *
 * Catalog sends an ``icon`` key (defaults to def id). Frontend looks up
 * ``src/assets/items/{key}.{svg|png|webp}``. Missing assets → null → show name.
 */

const iconModules = import.meta.glob('../assets/items/**/*.{svg,png,webp}', {
  eager: true,
  import: 'default',
}) as Record<string, string>

const ICON_BY_KEY = new Map<string, string>()

for (const [path, url] of Object.entries(iconModules)) {
  const file = path.split('/').pop() || ''
  const key = file.replace(/\.(svg|png|webp)$/i, '')
  if (key) ICON_BY_KEY.set(key, url)
}

/**
 * Normalize API icon / ui_key to a lookup key (basename, no extension).
 */
export function normalizeItemIconKey(icon: string | null | undefined): string {
  const raw = String(icon || '').trim().replace(/\\/g, '/')
  if (!raw) return ''
  const base = raw.split('/').pop() || raw
  return base.replace(/\.(svg|png|webp)$/i, '')
}

/**
 * Return a bundled asset URL when the icon file exists; otherwise null.
 */
export function resolveItemIconUrl(icon: string | null | undefined): string | null {
  const key = normalizeItemIconKey(icon)
  if (!key) return null
  return ICON_BY_KEY.get(key) ?? null
}

/** True when a local asset is registered for this icon key. */
export function hasItemIconAsset(icon: string | null | undefined): boolean {
  return resolveItemIconUrl(icon) != null
}
