/**
 * Shared rarity / 品阶 display helpers.
 *
 * Visual contract (see 开发计划.md §0.0.3):
 * - List chips: convey tier by color only (left bar + border); do not print 白/绿.
 * - Hover / detail: solid accent badge with Chinese name (粗糙…太古 or domain label_zh).
 * - Body text on light fill stays near-black for contrast.
 */

export type RarityTier =
  | 'gray'
  | 'white'
  | 'green'
  | 'blue'
  | 'purple'
  | 'orange'
  | 'red'

type RarityUi = {
  accent: string
  badgeText: string
  label_zh: string
}

const RARITY_UI: Record<RarityTier, RarityUi> = {
  gray: { accent: '#6b7280', badgeText: '#ffffff', label_zh: '粗糙' },
  white: { accent: '#64748b', badgeText: '#ffffff', label_zh: '普通' },
  green: { accent: '#15803d', badgeText: '#ffffff', label_zh: '优秀' },
  blue: { accent: '#1d4ed8', badgeText: '#ffffff', label_zh: '精良' },
  purple: { accent: '#7e22ce', badgeText: '#ffffff', label_zh: '史诗' },
  orange: { accent: '#c2410c', badgeText: '#ffffff', label_zh: '传说' },
  red: { accent: '#b91c1c', badgeText: '#ffffff', label_zh: '太古' },
}

/** Map domain ids / legacy color names / dao pet aliases → canonical tier. */
const RARITY_ALIASES: Record<string, RarityTier> = {
  gray: 'gray',
  rough: 'gray',
  粗糙: 'gray',
  灰: 'gray',

  white: 'white',
  common: 'white',
  normal: 'white',
  普通: 'white',
  凡品: 'white',
  白: 'white',

  green: 'green',
  uncommon: 'green',
  fine: 'green',
  优秀: 'green',
  良品: 'green',
  灵品: 'green',
  绿: 'green',

  blue: 'blue',
  rare: 'blue',
  精良: 'blue',
  上品: 'blue',
  玄品: 'blue',
  蓝: 'blue',

  purple: 'purple',
  epic: 'purple',
  superb: 'purple',
  史诗: 'purple',
  极品: 'purple',
  地品: 'purple',
  紫: 'purple',

  orange: 'orange',
  legendary: 'orange',
  legend: 'orange',
  传说: 'orange',
  天品: 'orange',
  橙: 'orange',

  red: 'red',
  mythic: 'red',
  ancient: 'red',
  primordial: 'red',
  太古: 'red',
  红: 'red',
}

const LEGACY_COLOR_LABELS = new Set(['灰', '白', '绿', '蓝', '紫', '橙', '红'])
const ENGLISH_ID_RE = /^[a-z][a-z0-9_]*$/i

const CHIP_TEXT = '#111827'
const CHIP_BG = '#ffffff'
const CHIP_BG_SELECTED = '#f3f4f6'

/**
 * Resolve any rarity id / label into a canonical UI tier.
 */
export function resolveRarityTier(rarity: string | null | undefined): RarityTier {
  const raw = String(rarity || '').trim()
  if (!raw) return 'white'
  const lower = raw.toLowerCase()
  if (lower in RARITY_ALIASES) return RARITY_ALIASES[lower]
  if (raw in RARITY_ALIASES) return RARITY_ALIASES[raw]
  return 'white'
}

function uiFor(rarity: string | null | undefined): RarityUi {
  return RARITY_UI[resolveRarityTier(rarity)]
}

/**
 * Chinese badge text: prefer domain label_zh unless it is a color name or raw English id.
 */
export function rarityLabelZh(
  rarity: string | null | undefined,
  labelFromApi?: string | null,
): string {
  const fallback = uiFor(rarity).label_zh
  const raw = String(labelFromApi || '').trim()
  if (!raw) return fallback
  if (LEGACY_COLOR_LABELS.has(raw)) return fallback
  if (ENGLISH_ID_RE.test(raw) && raw.toLowerCase() in RARITY_ALIASES) return fallback
  return raw
}

/** @deprecated Prefer {@link rarityLabelZh}; kept for techniqueCraft call sites. */
export function affixRarityLabelZh(
  rarity: string | null | undefined,
  labelFromApi?: string | null,
): string {
  return rarityLabelZh(rarity, labelFromApi)
}

export function rarityChipStyle(
  rarity: string | null | undefined,
  selected = false,
): Record<string, string> {
  const accent = uiFor(rarity).accent
  return {
    borderColor: accent,
    borderWidth: selected ? '2px' : '1.5px',
    borderStyle: 'solid',
    color: CHIP_TEXT,
    backgroundColor: selected ? CHIP_BG_SELECTED : CHIP_BG,
    fontWeight: selected ? '700' : '600',
    boxShadow: selected ? `inset 3px 0 0 ${accent}` : `inset 2px 0 0 ${accent}`,
  }
}

/** @deprecated Prefer {@link rarityChipStyle}. */
export function affixRarityChipStyle(
  rarity: string | null | undefined,
  selected = false,
): Record<string, string> {
  return rarityChipStyle(rarity, selected)
}

export function rarityTextColor(_rarity?: string | null): string {
  return CHIP_TEXT
}

/** @deprecated Prefer {@link rarityTextColor}. */
export function affixRarityTextColor(_rarity?: string | null): string {
  return CHIP_TEXT
}

export function rarityAccentColor(rarity: string | null | undefined): string {
  return uiFor(rarity).accent
}

/** @deprecated Prefer {@link rarityAccentColor}. */
export function affixRarityAccentColor(rarity: string | null | undefined): string {
  return rarityAccentColor(rarity)
}

export function rarityBadgeStyle(
  rarity: string | null | undefined,
): Record<string, string> {
  const ui = uiFor(rarity)
  return {
    borderColor: ui.accent,
    color: ui.badgeText,
    backgroundColor: ui.accent,
  }
}

/** @deprecated Prefer {@link rarityBadgeStyle}. */
export function affixRarityBadgeStyle(
  rarity: string | null | undefined,
): Record<string, string> {
  return rarityBadgeStyle(rarity)
}

export function rarityPanelStyle(
  rarity: string | null | undefined,
): Record<string, string> {
  const accent = rarityAccentColor(rarity)
  return {
    borderLeft: `4px solid ${accent}`,
    background: `color-mix(in srgb, ${accent} 8%, #ffffff)`,
    padding: '0.65rem 0.75rem',
    borderRadius: '8px',
  }
}

/** @deprecated Prefer {@link rarityPanelStyle}. */
export function affixRarityPanelStyle(
  rarity: string | null | undefined,
): Record<string, string> {
  return rarityPanelStyle(rarity)
}
