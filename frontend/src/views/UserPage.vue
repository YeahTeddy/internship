<template>
  <div class="user-page">
    <div class="page-header">
      <h2>用户管理</h2>
    </div>

    <!-- 用户列表 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>用户列表</span>
          <el-input v-model="keyword" placeholder="搜索用户名/邮箱" style="width: 200px" clearable @clear="loadUsers" @keyup.enter="loadUsers" />
        </div>
      </template>
      <el-table :data="users" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" width="120" />
        <el-table-column prop="email" label="邮箱" width="180" />
        <el-table-column label="角色" width="200">
          <template #default="{ row }">
            <el-tag v-for="r in row.roles" :key="r.id" size="small" style="margin-right: 4px">
              {{ r.display_name }}
            </el-tag>
            <span v-if="!row.roles || row.roles.length === 0" style="color: #999">无角色</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openRoleDrawer(row)">角色</el-button>
            <el-button link type="warning" @click="resetPassword(row)">重置密码</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination">
        <el-pagination v-model:current-page="page" :page-size="10" :total="total" layout="total, prev, pager, next" @current-change="loadUsers" />
      </div>
    </el-card>

    <!-- 角色分配抽屉 -->
    <el-drawer v-model="roleDrawerVisible" :title="`${selectedUser?.username || ''} 的角色`" size="350px">
      <div v-if="selectedUser">
        <el-checkbox-group v-model="selectedRoleIds" @change="handleRoleChange">
          <div v-for="role in allRoles" :key="role.id" style="padding: 12px 0; border-bottom: 1px solid #f0f0f0">
            <el-checkbox :label="role.id">
              <strong>{{ role.display_name }}</strong>
              <div style="font-size: 12px; color: #999">{{ role.description || role.name }}</div>
            </el-checkbox>
          </div>
        </el-checkbox-group>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'
import request from '@/utils/request'

const users = ref([])
const loading = ref(false)
const keyword = ref('')
const page = ref(1)
const total = ref(0)

const roleDrawerVisible = ref(false)
const selectedUser = ref(null)
const selectedRoleIds = ref([])
const allRoles = ref([])

async function loadUsers() {
  loading.value = true
  try {
    const res = await request.get('/user/list', { params: { page: page.value, keyword: keyword.value } })
    users.value = res.items || res.users || []
    total.value = res.total || 0
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

async function loadRoles() {
  try {
    const res = await request.get('/role/list')
    allRoles.value = res.roles || []
  } catch (e) { console.error(e) }
}

async function openRoleDrawer(user) {
  selectedUser.value = user
  try {
    const res = await request.get(`/user/${user.id}/roles`)
    selectedRoleIds.value = (res.roles || []).map(r => r.id)
    roleDrawerVisible.value = true
  } catch (e) { console.error(e) }
}

async function handleRoleChange(roleIds) {
  if (!selectedUser.value) return
  try {
    await request.post(`/user/${selectedUser.value.id}/roles`, { role_ids: roleIds })
    ElMessage.success('角色已更新')
    loadUsers()
  } catch (e) { console.error(e) }
}

async function resetPassword(user) {
  ElMessage.info('重置密码功能开发中')
}

onMounted(() => { loadUsers(); loadRoles() })
</script>

<style lang="scss" scoped>
.user-page { padding: 0; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; h2 { margin: 0; } }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.pagination { display: flex; justify-content: flex-end; margin-top: 16px; }
</style>
