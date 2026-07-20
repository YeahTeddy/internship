<template>
  <div class="role-page">
    <div class="page-header">
      <h2>角色管理</h2>
      <el-button type="primary" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon>新建角色
      </el-button>
    </div>

    <!-- 角色列表 -->
    <el-card shadow="never">
      <el-table :data="roles" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="角色名" width="120" />
        <el-table-column prop="display_name" label="显示名" width="120" />
        <el-table-column prop="description" label="描述" width="200" />
        <el-table-column label="系统角色" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.is_system" type="info" size="small">系统</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openPermDrawer(row)">权限</el-button>
            <el-button link type="danger" @click="deleteRole(row)" :disabled="row.is_system">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建角色对话框 -->
    <el-dialog v-model="showCreateDialog" title="新建角色" width="400px">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="角色名"><el-input v-model="createForm.name" placeholder="如 operator" /></el-form-item>
        <el-form-item label="显示名"><el-input v-model="createForm.display_name" placeholder="如 操作员" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="createForm.description" placeholder="可选" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="createRole">确定</el-button>
      </template>
    </el-dialog>

    <!-- 权限分配抽屉 -->
    <el-drawer v-model="permDrawerVisible" :title="`${selectedRole?.display_name || ''} 的权限`" size="450px">
      <div v-if="selectedRole">
        <el-checkbox-group v-model="selectedPermIds" @change="handlePermChange">
          <template v-for="(perms, module) in groupedPerms" :key="module">
            <h4 style="margin: 12px 0 8px; color: #409eff">{{ module }}</h4>
            <div v-for="p in perms" :key="p.id" style="padding: 6px 0; border-bottom: 1px solid #f5f5f5">
              <el-checkbox :label="p.id">
                <strong>{{ p.code }}</strong>
                <span style="margin-left: 8px; color: #999">{{ p.name }}</span>
              </el-checkbox>
            </div>
          </template>
        </el-checkbox-group>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import request from '@/utils/request'

const roles = ref([])
const loading = ref(false)
const showCreateDialog = ref(false)
const createForm = reactive({ name: '', display_name: '', description: '' })

const permDrawerVisible = ref(false)
const selectedRole = ref(null)
const selectedPermIds = ref([])
const allPerms = ref([])

const groupedPerms = computed(() => {
  const groups = {}
  for (const p of allPerms.value) {
    if (!groups[p.module]) groups[p.module] = []
    groups[p.module].push(p)
  }
  return groups
})

async function loadRoles() {
  loading.value = true
  try {
    const res = await request.get('/role/list')
    roles.value = res.roles || []
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

async function createRole() {
  if (!createForm.name || !createForm.display_name) {
    ElMessage.warning('请填写角色名和显示名')
    return
  }
  try {
    await request.post('/role', null, {
      params: { name: createForm.name, display_name: createForm.display_name, description: createForm.description },
    })
    ElMessage.success('角色创建成功')
    showCreateDialog.value = false
    createForm.name = ''; createForm.display_name = ''; createForm.description = ''
    loadRoles()
  } catch (e) { console.error(e) }
}

async function deleteRole(role) {
  try {
    await ElMessageBox.confirm(`确定删除角色 "${role.display_name}" 吗？`, '删除确认', { type: 'warning' })
    await request.delete(`/role/${role.id}`)
    ElMessage.success('角色已删除')
    loadRoles()
  } catch (e) { if (e !== 'cancel') console.error(e) }
}

async function openPermDrawer(role) {
  selectedRole.value = role
  try {
    const res = await request.get(`/role/${role.id}/permissions`)
    selectedPermIds.value = (res.permissions || []).map(p => p.id)
    permDrawerVisible.value = true
  } catch (e) { console.error(e) }
}

async function loadPermissions() {
  try {
    const res = await request.get('/permission/list')
    allPerms.value = res.permissions || []
  } catch (e) { console.error(e) }
}

async function handlePermChange(permIds) {
  if (!selectedRole.value) return
  try {
    await request.post(`/role/${selectedRole.value.id}/permissions`, { permission_ids: permIds })
    ElMessage.success('权限已更新')
  } catch (e) { console.error(e) }
}

onMounted(() => { loadRoles(); loadPermissions() })
</script>

<style lang="scss" scoped>
.role-page { padding: 0; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; h2 { margin: 0; } }
</style>
