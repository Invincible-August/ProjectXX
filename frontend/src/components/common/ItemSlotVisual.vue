<script setup lang="ts">
/**
 * Slot / picker cell visual (§0.0.4): icon when asset exists, else Chinese name.
 */
import { computed, ref, watch } from 'vue'
import { resolveItemIconUrl } from '../../utils/itemIcon'

const props = withDefaults(
  defineProps<{
    name: string
    icon?: string | null
    /** Empty-slot / placeholder text when name is empty */
    emptyText?: string
  }>(),
  { icon: null, emptyText: '空' },
)

const broken = ref(false)
const src = computed(() => resolveItemIconUrl(props.icon))
const showIcon = computed(() => Boolean(src.value) && !broken.value)
const caption = computed(() => {
  const n = String(props.name || '').trim()
  return n || props.emptyText
})

watch(
  () => props.icon,
  () => {
    broken.value = false
  },
)

function onImgError(): void {
  broken.value = true
}
</script>

<template>
  <span class="item-slot-visual" :class="{ 'has-icon': showIcon }">
    <img
      v-if="showIcon && src"
      class="item-slot-icon"
      :src="src"
      :alt="caption"
      draggable="false"
      @error="onImgError"
    />
    <span v-else class="item-slot-name">{{ caption }}</span>
  </span>
</template>

<style scoped>
.item-slot-visual {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  pointer-events: none;
}

.item-slot-icon {
  max-width: 85%;
  max-height: 85%;
  object-fit: contain;
  display: block;
}

.item-slot-name {
  display: block;
  width: 100%;
  padding: 0 0.1rem;
  font-size: 11px;
  line-height: 1.15;
  text-align: center;
  color: inherit;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
</style>
