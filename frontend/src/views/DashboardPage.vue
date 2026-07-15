<template>
  <div class="dashboard-page">
    <div class="page-header">
      <h2>数据看板</h2>
      <el-radio-group v-model="periodDays" size="default" @change="loadAllData">
        <el-radio-button :value="7">近 7 天</el-radio-button>
        <el-radio-button :value="30">近 30 天</el-radio-button>
        <el-radio-button :value="90">近 90 天</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 数字统计卡片 -->
    <el-row :gutter="16" class="stat-cards">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon" style="background: #ecf5ff"><el-icon :size="28" color="#409eff"><Document /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.total_tasks }}</div>
            <div class="stat-label">检测任务</div>
            <div class="stat-growth" :class="growthClass('tasks')">{{ formatGrowth(stats.growth?.tasks) }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon" style="background: #f0f9eb"><el-icon :size="28" color="#67c23a"><PictureFilled /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ formatNumber(stats.total_images) }}</div>
            <div class="stat-label">处理图片</div>
            <div class="stat-growth" :class="growthClass('images')">{{ formatGrowth(stats.growth?.images) }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon" style="background: #fdf6ec"><el-icon :size="28" color="#e6a23c"><Aim /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ formatNumber(stats.total_objects) }}</div>
            <div class="stat-label">检测目标</div>
            <div class="stat-growth" :class="growthClass('objects')">{{ formatGrowth(stats.growth?.objects) }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon" style="background: #fef0f0"><el-icon :size="28" color="#f56c6c"><Timer /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.avg_inference_time }}<span class="unit">ms</span></div>
            <div class="stat-label">平均耗时</div>
            <div class="stat-growth" :class="growthClass('inference_time', true)">{{ formatGrowth(stats.growth?.inference_time) }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区域 -->
    <el-row :gutter="16" class="chart-row">
      <el-col :span="16">
        <el-card shadow="hover"><template #header><span>每日检测趋势</span></template>
          <div ref="trendChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover"><template #header><span>类别分布</span></template>
          <div ref="classChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="chart-row">
      <el-col :span="12">
        <el-card shadow="hover"><template #header><span>场景分布</span></template>
          <div ref="sceneChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover"><template #header><span>任务类型分布</span></template>
          <div ref="typeChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { getClassDistribution, getSceneDistribution, getStatistics, getTrend, getTypeDistribution } from "@/api/dashboard";
import { Aim, Document, PictureFilled, Timer } from "@element-plus/icons-vue";
import * as echarts from "echarts";
import { onBeforeUnmount, onMounted, ref } from "vue";

const periodDays = ref(30);
const stats = ref({ total_tasks: 0, total_images: 0, total_objects: 0, avg_inference_time: 0, growth: {} });
const trendChartRef = ref(null);
const classChartRef = ref(null);
const sceneChartRef = ref(null);
const typeChartRef = ref(null);
let trendChart = null, classChart = null, sceneChart = null, typeChart = null;

function formatNumber(num) {
  if (!num) return "0";
  if (num >= 10000) return (num / 10000).toFixed(1) + "w";
  if (num >= 1000) return (num / 1000).toFixed(1) + "k";
  return String(num);
}

function formatGrowth(value) {
  if (value === undefined || value === null) return "";
  if (value > 0) return `+${value}%`;
  if (value < 0) return `${value}%`;
  return "持平";
}

function growthClass(key, inverse = false) {
  const val = stats.value.growth?.[key];
  if (val === undefined || val === null || val === 0) return "growth-flat";
  if (inverse) return val < 0 ? "growth-up" : "growth-down";
  return val > 0 ? "growth-up" : "growth-down";
}

async function loadAllData() {
  const days = periodDays.value;
  try {
    const [statsRes, trendRes, classRes, sceneRes, typeRes] = await Promise.all([
      getStatistics(days), getTrend(days), getClassDistribution(days),
      getSceneDistribution(days), getTypeDistribution(days),
    ]);
    stats.value = statsRes;
    renderTrendChart(trendRes.trend);
    renderClassChart(classRes.distribution);
    renderSceneChart(sceneRes.distribution);
    renderTypeChart(typeRes.distribution);
  } catch (err) { console.error("[看板数据加载失败]", err); }
}

function renderTrendChart(trend) {
  if (!trendChart) trendChart = echarts.init(trendChartRef.value);
  const dates = trend.map(d => d.date.slice(5));
  trendChart.setOption({
    tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
    legend: { data: ["检测任务", "检测目标"], bottom: 0 },
    grid: { left: 50, right: 20, top: 20, bottom: 40 },
    xAxis: { type: "category", data: dates },
    yAxis: [
      { type: "value", name: "任务数" },
      { type: "value", name: "目标数" },
    ],
    series: [
      { name: "检测任务", type: "line", data: trend.map(d => d.task_count), smooth: true, lineStyle: { width: 2 }, itemStyle: { color: "#409eff" }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: "rgba(64,158,255,0.3)" }, { offset: 1, color: "rgba(64,158,255,0.02)" }]) } },
      { name: "检测目标", type: "line", yAxisIndex: 1, data: trend.map(d => d.object_count), smooth: true, lineStyle: { width: 2 }, itemStyle: { color: "#67c23a" }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: "rgba(103,194,58,0.3)" }, { offset: 1, color: "rgba(103,194,58,0.02)" }]) } },
    ],
  });
}

function renderClassChart(distribution) {
  if (!classChart) classChart = echarts.init(classChartRef.value);
  classChart.setOption({
    tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
    legend: { type: "scroll", orient: "vertical", right: 10, top: 20, bottom: 20 },
    series: [{ type: "pie", radius: "65%", center: ["35%", "50%"], data: distribution, label: { formatter: "{b}\n{d}%", fontSize: 12 } }],
  });
}

function renderSceneChart(distribution) {
  if (!sceneChart) sceneChart = echarts.init(sceneChartRef.value);
  sceneChart.setOption({
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: 80, right: 20, top: 20, bottom: 30 },
    xAxis: { type: "value" },
    yAxis: { type: "category", data: distribution.map(d => d.name) },
    series: [{ type: "bar", data: distribution.map(d => d.value), barWidth: "50%", itemStyle: { borderRadius: [0, 4, 4, 0], color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: "#409eff" }, { offset: 1, color: "#79bbff" }]) }, label: { show: true, position: "right" } }],
  });
}

function renderTypeChart(distribution) {
  if (!typeChart) typeChart = echarts.init(typeChartRef.value);
  typeChart.setOption({
    tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
    legend: { bottom: 0 },
    color: ["#409eff", "#67c23a", "#e6a23c", "#f56c6c", "#909399"],
    series: [{ type: "pie", radius: ["40%", "65%"], data: distribution, label: { formatter: "{b}\n{d}%" } }],
  });
}

function handleResize() { trendChart?.resize(); classChart?.resize(); sceneChart?.resize(); typeChart?.resize(); }

onMounted(() => { loadAllData(); window.addEventListener("resize", handleResize); });
onBeforeUnmount(() => { window.removeEventListener("resize", handleResize); trendChart?.dispose(); classChart?.dispose(); sceneChart?.dispose(); typeChart?.dispose(); });
</script>

<style lang="scss" scoped>
.dashboard-page { padding: 0; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; h2 { margin: 0; } }
.stat-cards { margin-bottom: 16px; }
.stat-card :deep(.el-card__body) { display: flex; align-items: center; gap: 16px; padding: 20px; }
.stat-icon { width: 56px; height: 56px; border-radius: 12px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.stat-info { flex: 1; min-width: 0; }
.stat-value { font-size: 28px; font-weight: 700; color: #303133; line-height: 1.2; .unit { font-size: 14px; font-weight: 400; color: #909399; margin-left: 2px; } }
.stat-label { font-size: 13px; color: #909399; margin-top: 2px; }
.stat-growth { font-size: 12px; margin-top: 4px; &.growth-up { color: #67c23a; &::before { content: "↑ "; } } &.growth-down { color: #f56c6c; &::before { content: "↓ "; } } &.growth-flat { color: #909399; } }
.chart-row { margin-bottom: 16px; }
.chart-container { height: 320px; width: 100%; }
</style>
