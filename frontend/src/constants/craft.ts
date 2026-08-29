/**
 * Workshop protocol mirrors (aligned with backend app.constants.craft / research).
 * These are protocol enums, not a content catalog.
 */

/** 成品单一属性（金木水火土风雷暗） */
export const CRAFT_ELEMENT_FILTERS: ReadonlyArray<{
  id: string
  label_zh: string
  border: string
}> = [
  { id: 'metal', label_zh: '金', border: '#c9a227' },
  { id: 'wood', label_zh: '木', border: '#3d8c40' },
  { id: 'water', label_zh: '水', border: '#2b6cb0' },
  { id: 'fire', label_zh: '火', border: '#c53030' },
  { id: 'earth', label_zh: '土', border: '#8d6e3d' },
  { id: 'wind', label_zh: '风', border: '#319795' },
  { id: 'thunder', label_zh: '雷', border: '#6b46c1' },
    { id: 'dark', label_zh: '暗', border: '#5c5470' },
]

/** 炼器部位组（对齐 backend app.constants.craft.CRAFT_EQUIP_SLOT_GROUPS） */
export const CRAFT_EQUIP_SLOT_FILTERS: ReadonlyArray<{
  id: string
  label_zh: string
}> = [
  { id: 'weapon', label_zh: '武器' },
  { id: 'head', label_zh: '头部' },
  { id: 'chest', label_zh: '胸甲' },
  { id: 'hands', label_zh: '护手' },
  { id: 'legs', label_zh: '腿甲' },
  { id: 'shoes', label_zh: '鞋履' },
  { id: 'accessory', label_zh: '饰品' },
  { id: 'fabao', label_zh: '法宝' },
]

/** 符箓功能（对齐 backend app.constants.research.TALISMAN_KINDS） */
export const CRAFT_TALISMAN_KIND_FILTERS: ReadonlyArray<{
  id: string
  label_zh: string
}> = [
  { id: 'buff', label_zh: '增益' },
  { id: 'offensive', label_zh: '攻击' },
  { id: 'curse', label_zh: '诅咒' },
]
