<template>
  <aside class="app-sidebar">
    <el-menu
      :default-active="activeMenu"
      :router="true"
      background-color="#304156"
      text-color="#bfcbd9"
      active-text-color="#409eff"
    >
      <el-menu-item
        v-for="item in visibleMenuItems"
        :key="item.path"
        :index="item.path"
      >
        <el-icon>
          <component :is="item.icon" />
        </el-icon>
        <span>{{ item.title }}</span>
      </el-menu-item>
    </el-menu>
  </aside>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  ChatDotRound,
  Camera,
  Cpu,
  Clock,
  DataAnalysis,
  Setting,
  User,
  Lock,
} from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import request from '@/utils/request'

const route = useRoute()
const userStore = useUserStore()
const userRoles = ref([])

/** 当前激活的菜单项 */
const activeMenu = computed(() => {
  return '/' + route.path.split('/')[1]
})

/** 侧边栏菜单配置（含权限标识） */
const menuItems = [
  { path: '/chat', title: '智能对话', icon: ChatDotRound, roles: null },
  { path: '/detection', title: '检测工作台', icon: Camera, roles: null },
  { path: '/training', title: '模型训练', icon: Cpu, roles: null },
  { path: '/history', title: '历史记录', icon: Clock, roles: null },
  { path: '/dashboard', title: '数据看板', icon: DataAnalysis, roles: null },
  { path: '/users', title: '用户管理', icon: User, roles: ['admin'] },
  { path: '/roles', title: '角色管理', icon: Lock, roles: ['admin'] },
  { path: '/settings', title: '系统设置', icon: Setting, roles: null },
]

/** 根据角色过滤可见菜单 */
const visibleMenuItems = computed(() => {
  return menuItems.filter(item => {
    if (!item.roles) return true // 无权限限制
    return item.roles.some(r => userRoles.value.includes(r))
  })
})

/** 获取当前用户角色 */
onMounted(async () => {
  try {
    const res = await request.get('/auth/me')
    userRoles.value = (res.roles || []).map(r => r.name || r)
  } catch (e) {
    console.error('获取用户角色失败', e)
  }
})
</script>

<style lang="scss" scoped>
.app-sidebar {
  width: $sidebar-width;
  height: 100%;
  background: $sidebar-bg;
  overflow-y: auto;

  .el-menu {
    border-right: none;
    height: 100%;
  }

  .el-menu-item {
    height: 50px;
    line-height: 50px;

    &.is-active {
      background-color: rgba(64, 158, 255, 0.15) !important;
    }

    &:hover {
      background-color: rgba(255, 255, 255, 0.05) !important;
    }
  }
}
</style>
