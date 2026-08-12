<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'

type Tab = '洞府' | '修行' | '游历' | '宗门' | '背包'

const activeTab = ref<Tab>('洞府')
const showProfile = ref(false)
const notice = ref('')
const elapsed = ref(3 * 3600 + 18 * 60 + 42)
const qi = ref(82)
const spirit = ref(286)
const stone = ref(12480)
const medicine = ref(12)
const tabs: { name: Tab; glyph: string }[] = [
  { name: '洞府', glyph: '⌂' },
  { name: '修行', glyph: '☯' },
  { name: '游历', glyph: '⌁' },
  { name: '宗门', glyph: '♜' },
  { name: '背包', glyph: '▣' },
]

let ticker: number | undefined
ticker = window.setInterval(() => {
  elapsed.value += 1
  qi.value = Math.min(100, qi.value + 0.03)
}, 1000)
onBeforeUnmount(() => window.clearInterval(ticker))

const timeText = computed(() => {
  const h = Math.floor(elapsed.value / 3600).toString().padStart(2, '0')
  const m = Math.floor(elapsed.value % 3600 / 60).toString().padStart(2, '0')
  const s = Math.floor(elapsed.value % 60).toString().padStart(2, '0')
  return `${h}:${m}:${s}`
})

function flash(message: string) {
  notice.value = message
  window.setTimeout(() => (notice.value = ''), 2400)
}

function collect() {
  const gain = 986
  stone.value += gain
  spirit.value += 36
  elapsed.value = 0
  flash(`已收取 ${gain.toLocaleString()} 灵石与 36 点修为`)
}

function useMedicine() {
  if (!medicine.value) return flash('百草囊中已无回元丹')
  medicine.value -= 1
  qi.value = Math.min(100, qi.value + 25)
  flash('服下回元丹，灵气恢复 25 点')
}

function switchTab(tab: Tab) {
  activeTab.value = tab
  if (tab !== '洞府') flash(`${tab}功能正在炼制中，暂以洞府总览展示`)
}
</script>

<template>
  <main class="game-shell">
    <div class="ambient ambient-one"></div>
    <div class="ambient ambient-two"></div>

    <section class="game-card">
      <header class="topbar">
        <button class="brand" aria-label="返回游戏首页" @click="activeTab = '洞府'">
          <span class="brand-seal">玄</span>
          <span><b>玄墨山海</b><small>XIĀN MÒ SHĀN HǍI</small></span>
        </button>
        <div class="world-status"><i></i> 仙缘正盛 <span>·</span> 乙巳年 · 惊蛰</div>
        <button class="avatar" aria-label="打开角色档案" @click="showProfile = true">
          <span>清</span><em>24</em>
        </button>
      </header>

      <div class="content-grid">
        <aside class="side-rail" aria-label="主导航">
          <button v-for="tab in tabs" :key="tab.name" :class="['nav-item', { active: activeTab === tab.name }]" @click="switchTab(tab.name)">
            <span class="nav-glyph">{{ tab.glyph }}</span><span>{{ tab.name }}</span>
          </button>
          <div class="rail-line"></div>
          <button class="nav-item"><span class="nav-glyph">⚙</span><span>设置</span></button>
        </aside>

        <div class="main-content">
          <section class="hero-panel">
            <div class="hero-ink"></div>
            <div class="hero-copy">
              <p class="eyebrow">当前所在 · 青霄洞府</p>
              <h1>一息入定，万象归元</h1>
              <p>灵脉澄澈，正是吐纳周天的绝佳时机。</p>
              <button class="text-button" @click="flash('已展开青霄洞府详情')">查看洞府 <span>→</span></button>
            </div>
            <div class="mountain-art" aria-hidden="true">
              <div class="moon"></div><div class="peak peak-far"></div><div class="peak peak-mid"></div><div class="peak peak-near"></div><div class="mist mist-a"></div><div class="mist mist-b"></div>
            </div>
          </section>

          <section class="cultivation-card panel">
            <div class="section-title"><div><p>修行进境</p><h2>炼气 · 九层</h2></div><span class="badge">突破在即</span></div>
            <div class="progress-row"><div class="progress-track"><span></span></div><strong>86%</strong></div>
            <p class="progress-caption">再积累 <b>1,284</b> 点修为，即可尝试筑基</p>
            <div class="stat-grid">
              <div><span class="stat-icon blue">✦</span><p>修为<small>{{ spirit.toLocaleString() }} / 3,200</small></p></div>
              <div><span class="stat-icon gold">♢</span><p>灵石<small>{{ stone.toLocaleString() }}</small></p></div>
              <div><span class="stat-icon rose">❋</span><p>灵气<small>{{ Math.floor(qi) }} / 100</small></p></div>
            </div>
          </section>

          <section class="afk-card panel">
            <div class="afk-top"><div><p class="eyebrow">正在挂机</p><h2>青霄灵脉</h2></div><span class="online-dot">灵脉运转中</span></div>
            <div class="afk-body">
              <div class="meditate-mark"><span>☯</span><i></i><i></i></div>
              <div class="gain-list"><p>已静修 <b>{{ timeText }}</b></p><div><span>✦ 修为 + 286</span><span>♢ 灵石 + 986</span></div><small>离线收益上限：8 小时</small></div>
            </div>
            <button class="primary-button" @click="collect">收取灵脉收益 <span>＋</span></button>
          </section>

          <section class="bottom-grid">
            <article class="schedule-card panel">
              <div class="section-title compact"><div><p>今日事宜</p><h2>修真日程</h2></div><button class="more" @click="flash('已查看完整日程')">全部 ›</button></div>
              <div class="schedule-list">
                <div><span class="calendar">惊<br>蛰</span><p><b>宗门试炼</b><small>每日 04:00 重置</small></p><button @click="flash('已前往宗门试炼')">前往</button></div>
                <div><span class="calendar faded">第<br>七</span><p><b>灵田采撷</b><small>可收获 3 株灵植</small></p><button @click="flash('灵田灵植已收进百草囊')">采撷</button></div>
              </div>
            </article>

            <article class="medicine-card panel">
              <div class="section-title compact"><div><p>随身灵物</p><h2>百草囊</h2></div><span class="count">{{ medicine }} 枚</span></div>
              <div class="bottle"><div class="bottle-cap"></div><div class="bottle-body"><span>丹</span></div><div class="leaf leaf-one">◆</div><div class="leaf leaf-two">✦</div></div>
              <div class="medicine-info"><p><b>回元丹</b><small>恢复 25 点灵气</small></p><button @click="useMedicine">服用</button></div>
            </article>
          </section>
        </div>
      </div>
    </section>

    <Transition name="toast"><p v-if="notice" class="toast">{{ notice }}</p></Transition>
    <div v-if="showProfile" class="modal-backdrop" @click.self="showProfile = false">
      <section class="profile-modal"><button class="close" @click="showProfile = false">×</button><div class="modal-avatar">清</div><p class="eyebrow">青霄洞府 · 内门弟子</p><h2>清玄子</h2><div class="profile-stats"><span>道龄 <b>24</b></span><span>境界 <b>炼气九层</b></span><span>灵根 <b>水木双灵根</b></span></div></section>
    </div>
  </main>
</template>
