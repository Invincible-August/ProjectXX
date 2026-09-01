<script setup lang="ts">
/**
 * 洞府枢纽：列出开放房间（工坊 / 研究室）+ 储物袋。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import InventoryPanel from '../components/workshop/InventoryPanel.vue'
import { fetchCaveOverviewApi } from '../api/cave'
import { CAVE_ROOM_PATHS } from '../constants/cave'
import { useInventoryStore } from '../stores/inventory'
import type { CaveRoomPublic } from '../types/cave'

const FALLBACK_ROOMS: CaveRoomPublic[] = [
  { id: 'workshop', label_zh: '工坊', summary_zh: '炼丹 / 炼器 / 符箓 / 傀儡' },
  { id: 'lab', label_zh: '研究室', summary_zh: '功法 / 阵盘 / 符箓图纸' },
]

const router = useRouter()
const inventoryStore = useInventoryStore()
const rooms = ref<CaveRoomPublic[]>(FALLBACK_ROOMS)
const loadError = ref('')

onMounted(async () => {
  loadError.value = ''
  void inventoryStore.load()
  const envelope = await fetchCaveOverviewApi()
  if (envelope.code === 0 && envelope.data?.rooms?.length) {
    rooms.value = envelope.data.rooms
    return
  }
  if (envelope.message) {
    loadError.value = envelope.message
  }
})

function enter(room: CaveRoomPublic): void {
  const path = CAVE_ROOM_PATHS[room.id]
  if (path) void router.push(path)
}
</script>

<template>
  <div class="hub">
    <el-alert
      v-if="loadError"
      :title="loadError"
      type="warning"
      show-icon
      :closable="false"
      class="hub-alert"
    />
    <div class="hub-grid">
      <div class="room-grid">
        <button
          v-for="room in rooms"
          :key="room.id"
          type="button"
          class="room-card"
          @click="enter(room)"
        >
          <el-text tag="b">{{ room.label_zh }}</el-text>
          <el-text type="info" size="small">{{ room.summary_zh }}</el-text>
        </button>
      </div>
      <InventoryPanel />
    </div>
  </div>
</template>

<style scoped>
.hub-alert {
  margin-bottom: 0.75rem;
}
.hub-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 360px);
  gap: 0.75rem;
  align-items: start;
}
.room-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 0.75rem;
}
.room-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.35rem;
  padding: 1rem 1.1rem;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-bg-color);
  cursor: pointer;
  text-align: left;
}
.room-card:hover {
  border-color: var(--el-color-primary);
}
@media (max-width: 800px) {
  .hub-grid {
    grid-template-columns: 1fr;
  }
}
</style>
