<template>
  <div class="chat-page">
    <!-- ── 消息列表区域 ── -->
    <div class="message-list" ref="messageListRef">
      <div
        v-for="(msg, index) in agentStore.messages"
        :key="index"
        :class="['message-item', `message-${msg.role}`]"
      >
        <!-- 用户消息 -->
        <div v-if="msg.role === 'user'" class="message-bubble user-bubble">
          <div class="message-content">{{ msg.content }}</div>
          <!-- 单张图片附件 -->
          <div v-if="msg.image" class="message-attachment">
            <img :src="msg.imagePreview" alt="附件图片" />
          </div>
          <!-- 多图附件（批量检测） -->
          <div v-if="msg.images && msg.images.length" class="message-attachments-grid">
            <img v-for="(src, i) in msg.images" :key="i" :src="src" alt="附件图片" />
          </div>
        </div>

        <!-- AI 消息 -->
        <div
          v-else-if="msg.role === 'assistant'"
          class="message-bubble assistant-bubble"
        >
          <div v-if="msg.loading" class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
          <div v-else-if="msg.thinking" class="thinking-indicator">
            🤔 {{ msg.thinkingContent || '正在思考...' }}
          </div>
          <div
            v-else
            class="message-content markdown-body"
            v-html="renderMarkdown(msg.content)"
          ></div>

          <!-- 检测结果卡片 -->
          <DetectionResultCard
            v-if="msg.detectionResult"
            :result="msg.detectionResult"
          />
        </div>

        <!-- 工具调用提示 -->
        <div v-if="msg.toolCall" class="tool-call-info">
          <el-tag v-if="msg.toolCall.status === 'running'" size="small" type="warning" effect="plain">
            🔧 正在调用: {{ msg.toolCall.tool }}...
          </el-tag>
          <el-tag v-else size="small" type="success" effect="plain">
            ✅ 已调用: {{ msg.toolCall.tool }}
            <span v-if="msg.toolCall.summary" style="margin-left: 4px; color: #67c23a">— {{ msg.toolCall.summary }}</span>
          </el-tag>
        </div>
      </div>
    </div>

    <!-- ── 快捷操作栏 ── -->
    <div class="quick-actions">
      <el-select v-model="selectedModelId" size="small" style="width: 160px" placeholder="选择模型">
        <el-option v-for="m in modelList" :key="m.id" :label="m.version + ' (' + m.map50 + ')'" :value="m.id" />
      </el-select>
      <el-button
        @click="handleQuickDetect('single')"
        :disabled="agentStore.isLoading"
      >
        📷 单图检测
      </el-button>
      <el-button
        @click="handleQuickDetect('batch')"
        :disabled="agentStore.isLoading"
      >
        📁 批量/ZIP
      </el-button>
      <el-button
        @click="handleVideoDetect"
        :disabled="agentStore.isLoading"
      >
        🎬 视频
      </el-button>
      <el-button disabled>📹 摄像头</el-button>
    </div>

    <!-- ── 输入区域 ── -->
    <div
      class="input-area"
      :class="{ 'drag-over': isDragOver }"
      @dragover.prevent="isDragOver = true"
      @dragleave.prevent="isDragOver = false"
      @drop.prevent="handleDrop"
    >
      <!-- 附件按钮 -->
      <el-button
        class="attach-btn"
        @click="triggerFileInput"
        :disabled="agentStore.isLoading"
        circle
      >
        📎
      </el-button>
      <input
        ref="fileInputRef"
        type="file"
        accept="image/*,.zip"
        style="display: none"
        @change="handleFileSelect"
      />

      <!-- 文本输入框 -->
      <el-input
        v-model="inputText"
        placeholder="输入消息，或拖拽图片/ZIP 到这里..."
        @keyup.enter="sendMessage"
        :disabled="agentStore.isLoading"
      />

      <!-- 发送/停止按钮 -->
      <el-button
        v-if="!agentStore.isLoading"
        type="primary"
        @click="sendMessage"
        :disabled="!inputText.trim() && !selectedFile"
      >
        发送
      </el-button>
      <el-button v-else type="danger" @click="handleStop"> 停止 </el-button>
    </div>
  </div>
</template>

<script setup>
/**
 * ChatPage.vue — 智能对话界面（Day 8）
 *
 * 功能：
 *   - 消息气泡（用户/AI 区分）
 *   - 文件附件上传（图片/ZIP 拖拽或选择）
 *   - SSE 流式渲染 AI 回复
 *   - 检测结果卡片展示
 *   - 快捷操作栏（单图/批量/视频/摄像头）
 *   - 中断当前对话
 */
import { detectBatch, detectSingle, detectVideo, detectZip, getModelList, getVideoStatus } from '@/api/detection'
import DetectionResultCard from '@/components/DetectionResultCard.vue'
import { useAgentStore } from '@/stores/agent'
import { renderMarkdown } from '@/utils/markdown'
import request from '@/utils/request'
import { streamChat } from '@/utils/stream'
import { ElMessage } from 'element-plus'
import { computed, nextTick, onMounted, ref } from 'vue'

// ── Store ──
const agentStore = useAgentStore()

// ── 响应式状态 ──
const inputText = ref('')
const selectedFile = ref(null)
const messageListRef = ref(null)
const fileInputRef = ref(null)
const isDragOver = ref(false)
const modelList = ref([])
const selectedModelId = ref(null)

// ── 计算属性 ──
const canSend = computed(() => {
  return inputText.value.trim() || selectedFile.value
})

// ── 方法 ──

/** 发送消息 */
async function sendMessage() {
  if (!canSend.value) return

  const fileToSend = selectedFile.value
  const message = inputText.value.trim() || (fileToSend ? '帮我检测这张图片' : '')
  const imagePreview = fileToSend ? URL.createObjectURL(fileToSend) : null

  // 添加用户消息到列表
  agentStore.addMessage({
    role: 'user',
    content: message,
    image: fileToSend ? fileToSend.name : null,
    imagePreview,
  })

  // 清空输入
  inputText.value = ''
  selectedFile.value = null

  // 添加 AI 加载占位
  agentStore.addMessage({
    role: 'assistant',
    content: '',
    loading: true,
  })

  agentStore.setLoading(true)
  scrollToBottom()

  // 如果有附件图片，先上传到服务端获取真实路径
  let serverImagePath = null
  if (fileToSend) {
    try {
      const formData = new FormData()
      formData.append('file', fileToSend)
      const uploadResult = await request.post('/chat/upload', formData, {
        headers: { 'Content-Type': undefined },
      })
      serverImagePath = uploadResult.image_path
    } catch (err) {
      console.error('[图片上传失败]', err.response?.data || err.message || err)
      const lastMsg = agentStore.messages[agentStore.messages.length - 1]
      lastMsg.content = `图片上传失败：${err.response?.data?.detail || err.message || '未知错误'}，请重试`
      lastMsg.loading = false
      lastMsg.error = true
      agentStore.setLoading(false)
      return
    }
  }

  // 发起 SSE 流式请求
  const requestBody = {
    message,
    ...(serverImagePath ? { image_path: serverImagePath } : {}),
  }

  let fullContent = ''

  const stop = streamChat('/api/chat/stream', requestBody, {
    onMessage: (data) => {
      if (data.type === 'text_chunk') {
        fullContent += data.content
        agentStore.updateLastAssistantMessage(fullContent)
        scrollToBottom()
      } else if (data.type === 'thinking') {
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        lastMsg.thinking = true
        lastMsg.thinkingContent = data.content
      } else if (data.type === 'tool_start' || data.type === 'tool_call') {
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        lastMsg.thinking = false
        lastMsg.toolCall = { tool: data.tool, input: data.input, status: 'running' }
        scrollToBottom()
      } else if (data.type === 'tool_end' || data.type === 'tool_result') {
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        if (lastMsg.toolCall) lastMsg.toolCall.status = 'done'
        try {
          const result = JSON.parse(data.result || '{}')
          if (result.detections) {
            lastMsg.detectionResult = result
            lastMsg.loading = false
          } else if (result.results) {
            lastMsg.knowledgeResult = result
          }
        } catch (e) {
          // 非 JSON 结果，忽略
        }
        scrollToBottom()
      } else if (data.type === 'done') {
        fullContent = data.full_text || fullContent
        agentStore.updateLastAssistantMessage(fullContent)
      } else if (data.type === 'error') {
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        lastMsg.content = data.content
        lastMsg.loading = false
        lastMsg.error = true
      }
    },
    onDone: () => {
      const lastMsg = agentStore.messages[agentStore.messages.length - 1]
      if (lastMsg.loading) lastMsg.loading = false
      agentStore.setLoading(false)
    },
    onError: (err) => {
      const lastMsg = agentStore.messages[agentStore.messages.length - 1]
      lastMsg.content = `抱歉，处理出错了：${err.message}`
      lastMsg.loading = false
      lastMsg.error = true
      agentStore.setLoading(false)
      ElMessage.error('对话请求失败，请重试')
    },
  })

  agentStore.abortController = stop
}

/** 停止生成 */
function handleStop() {
  agentStore.abort()
  const lastMsg = agentStore.messages[agentStore.messages.length - 1]
  if (lastMsg.loading) {
    lastMsg.loading = false
    lastMsg.content += '\n[已停止生成]'
  }
}

/** 触发文件选择框 */
function triggerFileInput() {
  fileInputRef.value?.click()
}

/** 文件选择回调 */
function handleFileSelect(event) {
  const file = event.target.files[0]
  if (file) {
    selectedFile.value = file
    file._tempPath = URL.createObjectURL(file)
    ElMessage.info(`${file.name} 已选择`)
  }
}

/** 拖拽文件处理 */
function handleDrop(event) {
  isDragOver.value = false
  const files = event.dataTransfer?.files
  if (!files || files.length === 0) return

  const file = files[0]
  const isImage = file.type.startsWith('image/')
  const isZip = file.name.endsWith('.zip')

  if (!isImage && !isZip) {
    ElMessage.warning('只支持图片或 ZIP 文件')
    return
  }

  selectedFile.value = file
  ElMessage.info(`${file.name} 已选择（拖拽）`)
}

/** 滚动到底部 */
function scrollToBottom() {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

/**
 * 快捷检测流程
 * 1. 用户点击快捷按钮
 * 2. 弹出文件选择框
 * 3. 选择文件后，调用对应 API
 * 4. 将结果以"用户消息 + AI 结果卡片"的形式插入对话
 */
async function handleQuickDetect(type) {
  if (type === 'single') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*'
    input.onchange = async (e) => {
      const file = e.target.files[0]
      if (!file) return

      agentStore.addMessage({
        role: 'user',
        content: `[快捷检测] ${file.name}`,
        image: file.name,
        imagePreview: URL.createObjectURL(file),
      })

      agentStore.addMessage({
        role: 'assistant',
        content: '正在检测中...',
        loading: true,
      })
      agentStore.setLoading(true)
      scrollToBottom()

      const formData = new FormData()
      formData.append('file', file)
      if (selectedModelId.value) formData.append('model_version_id', selectedModelId.value)

      try {
        const result = await detectSingle(formData)
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        lastMsg.content = `检测完成！发现 ${result.total_objects} 个目标。`
        lastMsg.loading = false
        lastMsg.detectionResult = result
      } catch (err) {
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        lastMsg.content = '检测失败，请重试'
        lastMsg.loading = false
        lastMsg.error = true
      } finally {
        agentStore.setLoading(false)
      }
    }
    input.click()
  } else if (type === 'batch') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*,.zip'
    input.multiple = true
    input.onchange = async (e) => {
      const files = Array.from(e.target.files)
      if (!files.length) return

      const isZip = files.some((f) => f.name.endsWith('.zip'))
      const formData = new FormData()

      if (isZip && files.length === 1) {
        formData.append('file', files[0])
        agentStore.addMessage({
          role: 'user',
          content: `[快捷检测] ZIP: ${files[0].name}`,
        })
      } else {
        files.forEach((f) => formData.append('files', f))
        const imagePreviews = files.map((f) => URL.createObjectURL(f))
        agentStore.addMessage({
          role: 'user',
          content: `[快捷检测] ${files.length} 张图片`,
          images: imagePreviews,
        })
      }
      if (selectedModelId.value) formData.append('model_version_id', selectedModelId.value)

      agentStore.addMessage({
        role: 'assistant',
        content: '正在批量检测中...',
        loading: true,
      })
      agentStore.setLoading(true)
      scrollToBottom()

      try {
        const apiCall = isZip ? detectZip(formData) : detectBatch(formData)
        const result = await apiCall
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]

        if (result.error) {
          lastMsg.content = `批量检测失败：${result.error}`
          lastMsg.loading = false
          lastMsg.error = true
          return
        }

        const totalObjects = result.total_objects ?? 0
        lastMsg.content = `批量检测完成！共 ${totalObjects} 个目标。`
        lastMsg.loading = false
        lastMsg.detectionResult = result
      } catch (err) {
        const lastMsg = agentStore.messages[agentStore.messages.length - 1]
        lastMsg.content = `批量检测失败：${err.message || err}`
        lastMsg.loading = false
        lastMsg.error = true
      } finally {
        agentStore.setLoading(false)
      }
    }
    input.click()
  }
}

/** 视频检测流程 */
async function handleVideoDetect() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'video/mp4,video/avi,video/quicktime,video/x-msvideo'
  input.onchange = async (e) => {
    const file = e.target.files[0]
    if (!file) return

    const maxSize = 50 * 1024 * 1024
    if (file.size > maxSize) {
      ElMessage.warning('视频文件不能超过 50MB')
      return
    }

    agentStore.addMessage({
      role: 'user',
      content: `[视频检测] ${file.name} (${(file.size / (1024 * 1024)).toFixed(1)}MB)`,
    })

    agentStore.addMessage({
      role: 'assistant',
      content: '正在上传视频...',
      loading: true,
    })
    agentStore.setLoading(true)
    scrollToBottom()

    const formData = new FormData()
    formData.append('file', file)
    if (selectedModelId.value) formData.append('model_version_id', selectedModelId.value)

    try {
      const uploadResult = await detectVideo(formData)
      const taskId = uploadResult.task_id
      const lastMsg = agentStore.messages[agentStore.messages.length - 1]
      lastMsg.content = '视频已上传，正在处理中...'
      await pollVideoProgress(taskId)
    } catch (err) {
      const lastMsg = agentStore.messages[agentStore.messages.length - 1]
      lastMsg.content = `视频检测失败：${err.message || err}`
      lastMsg.loading = false
      lastMsg.error = true
      agentStore.setLoading(false)
    }
  }
  input.click()
}

/** 轮询视频检测进度 */
async function pollVideoProgress(taskId) {
  const maxPolls = 300
  let polls = 0

  const poll = async () => {
    if (polls++ > maxPolls) {
      const lastMsg = agentStore.messages[agentStore.messages.length - 1]
      lastMsg.content = '视频处理超时，请稍后查看结果'
      lastMsg.loading = false
      agentStore.setLoading(false)
      return
    }

    try {
      const status = await getVideoStatus(taskId)
      const lastMsg = agentStore.messages[agentStore.messages.length - 1]

      if (status.status === 'completed') {
        lastMsg.content = `视频检测完成！共处理 ${status.result?.processed_frames || 0} 帧，发现 ${status.result?.total_objects || 0} 个目标。`
        lastMsg.loading = false
        if (status.result) {
          lastMsg.detectionResult = { ...status.result, type: 'video' }
        }
        agentStore.setLoading(false)
      } else if (status.status === 'failed') {
        lastMsg.content = `视频检测失败：${status.message}`
        lastMsg.loading = false
        lastMsg.error = true
        agentStore.setLoading(false)
      } else {
        lastMsg.content = `视频处理中... ${status.message || ''}`
        setTimeout(poll, 2000)
      }
    } catch (err) {
      setTimeout(poll, 3000)
    }
  }

  await poll()
}

/** 加载可用模型列表 */
async function loadModels() {
  try {
    const res = await getModelList()
    modelList.value = res.models || []
    // 默认选中 is_default 的模型
    const defaultModel = modelList.value.find(m => m.is_default)
    if (defaultModel) {
      selectedModelId.value = defaultModel.id
    }
  } catch (err) {
    console.error('[加载模型列表失败]', err)
  }
}

onMounted(() => {
  loadModels()
  if (agentStore.messages.length === 0) {
    agentStore.addMessage({
      role: 'assistant',
      content:
        '你好！我是 RSOD 目标检测智能体助手。\n\n你可以：\n- 上传一张图片，让我帮你检测目标\n- 使用下方的快捷按钮直接触发检测\n- 用自然语言描述你的需求\n\n试试发一张图片给我吧！',
    })
  }
})
</script>

<style lang="scss" scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f5f5f5;
}

/* ── 消息列表 ── */
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.message-item {
  display: flex;
  margin-bottom: 16px;

  &.message-user {
    justify-content: flex-end;
  }

  &.message-assistant {
    justify-content: flex-start;
  }
}

.message-bubble {
  max-width: 70%;
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.5;
  word-break: break-word;
}

.user-bubble {
  background: #409eff;
  color: white;
  border-bottom-right-radius: 4px;
}

.assistant-bubble {
  background: white;
  border: 1px solid #e0e0e0;
  border-bottom-left-radius: 4px;
}

.message-content {
  white-space: pre-wrap;
}

.markdown-body {
  h1, h2, h3 {
    margin-top: 8px;
    margin-bottom: 4px;
  }
  table {
    border-collapse: collapse;
    width: 100%;
    margin: 8px 0;
  }
  th, td {
    border: 1px solid #e0e0e0;
    padding: 4px 8px;
  }
  code {
    background: #f0f0f0;
    padding: 2px 4px;
    border-radius: 3px;
  }
}

.typing-indicator {
  display: flex;
  gap: 4px;

  span {
    width: 6px;
    height: 6px;
    background: #999;
    border-radius: 50%;
    animation: typing 1.2s infinite;
  }

  span:nth-child(2) { animation-delay: 0.2s; }
  span:nth-child(3) { animation-delay: 0.4s; }
}

/* ── 快捷操作栏 ── */
.quick-actions {
  display: flex;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid #e0e0e0;
  background: white;
}

/* ── 输入区域 ── */
.input-area {
  display: flex;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid #e0e0e0;
  background: white;
  transition: background 0.2s, border-color 0.2s;

  .el-input {
    flex: 1;
  }

  &.drag-over {
    background: #ecf5ff;
    border-top-color: #409eff;
  }
}

/* ── 附件预览 ── */
.message-attachment {
  margin-top: 8px;

  img {
    max-width: 200px;
    border-radius: 8px;
    border: 1px solid #e0e0e0;
  }
}

/* ── 多图附件网格 ── */
.message-attachments-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
  gap: 8px;
  margin-top: 8px;

  img {
    width: 100%;
    height: 80px;
    object-fit: cover;
    border-radius: 6px;
    border: 1px solid #e0e0e0;
  }
}

/* ── 工具调用信息 ── */
.tool-call-info {
  margin-top: 8px;
  padding: 4px 8px;
  background: #f5f5f5;
  border-radius: 4px;
  font-size: 12px;
  color: #666;
}

.thinking-indicator {
  color: #909399;
  font-size: 13px;
  font-style: italic;
  padding: 4px 0;
}

@keyframes typing {
  0%, 60%, 100% { opacity: 0.3; transform: translateY(0); }
  30% { opacity: 1; transform: translateY(-4px); }
}
</style>
