/**
 * 把化身面板映射成 CharacterPanel 可用的 CharacterPublic。
 */
import type { AvatarPublic } from '../types/avatar'
import type { CharacterPublic } from '../types/character'
import { idleDirectionLabel } from './idleLabels'

/**
 * Overlay avatar pools/attrs onto the owner's character DTO for the summary panel.
 *
 * @param owner - 本体权威
 * @param avatar - 化身面板
 */
export function avatarAsCharacter(
  owner: CharacterPublic,
  avatar: AvatarPublic,
): CharacterPublic {
  return {
    ...owner,
    name: avatar.name,
    cultivation_points: avatar.cultivation_points,
    body_tempering_points: avatar.body_tempering_points,
    crafting_exp: avatar.crafting_exp,
    idle_direction: String(avatar.idle_direction),
    idle_direction_name: idleDirectionLabel(String(avatar.idle_direction)),
    combat: avatar.combat ?? owner.combat,
    life: avatar.life ?? owner.life,
    hp_max: avatar.hp_max ?? avatar.combat?.final?.hp ?? owner.hp_max,
    hp_current: avatar.hp_current ?? avatar.hp_max ?? avatar.combat?.final?.hp ?? owner.hp_max,
    mp_max: avatar.mp_max ?? avatar.combat?.final?.mp ?? owner.mp_max,
    mp_current: avatar.mp_current ?? avatar.mp_max ?? avatar.combat?.final?.mp ?? owner.mp_max,
    has_avatar: false,
    avatar_summary: undefined,
    divine_sense: undefined,
    dual_idle_preview: undefined,
    // 化身独立大道；未开道为 null，不套用本体
    dao: avatar.dao ?? null,
    reincarnation_points: 0,
    reincarnation_count: undefined,
    breakthrough_grade_name: '',
    battle_stamina: avatar.stamina
      ? {
          left: avatar.stamina.stamina,
          cap: avatar.stamina.stamina_cap,
          regen_per_minute: 0,
        }
      : owner.battle_stamina,
  }
}
