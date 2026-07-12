<template>
  <div class="dashboard">
    <h2>📊 仪表盘总览</h2>
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6" v-for="s in stats" :key="s.label">
        <el-card shadow="hover" :body-style="{ padding: '20px' }">
          <div class="stat-card">
            <div class="stat-value" :style="{ color: s.color }">{{ s.value }}</div>
            <div class="stat-label">{{ s.label }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="16">
        <el-card>
          <template #header>📈 生产趋势 (近7天)</template>
          <v-chart :option="chartOption" style="height: 300px" autoresize />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <template #header>🔔 设备状态</template>
          <div v-if="devices.length">
            <div v-for="d in devices" :key="d.hardwareSn" style="display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid #eee">
              <span>{{ d.deviceName?.slice(0, 12) }}...</span>
              <el-tag :type="d.status==='online' ? 'success' : 'info'" size="small">
                {{ d.status==='online' ? '🟢 在线' : '⚪ 离线' }}
              </el-tag>
            </div>
          </div>
          <div v-else style="color: #67c23a">✅ 所有设备正常</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import axios from '../api'

use([CanvasRenderer, LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent])

const stats = ref([
  { label: '在线设备', value: '—', color: '#67c23a' },
  { label: '总设备数', value: '—', color: '#409eff' },
  { label: '累计产量', value: '—', color: '#e6a23c' },
  { label: '在线率', value: '—', color: '#909399' },
])
const devices = ref([])
const chartOption = ref({})

onMounted(async () => {
  try {
    const res = await axios.get('/api/device/cluster')
    const d = res.data?.data || {}
    stats.value = [
      { label: '在线设备', value: d.onlineDevices ?? '—', color: '#67c23a' },
      { label: '总设备数', value: d.totalDevices ?? '—', color: '#409eff' },
      { label: '累计产量', value: (d.totalProduction ?? 0).toLocaleString(), color: '#e6a23c' },
      { label: '在线率', value: (d.onlineRate ?? '—') + '%', color: '#909399' },
    ]
    devices.value = d.devices || []
  } catch(e) {
    console.warn('Dashboard API 未连接，显示演示数据')
  }

  chartOption.value = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: ['周一','周二','周三','周四','周五','周六','周日'] },
    yAxis: { type: 'value' },
    series: [
      { name: '良品', type: 'line', data: [820,932,901,934,1290,1330,1200], smooth: true, itemStyle: { color: '#67c23a' } },
      { name: '不良', type: 'line', data: [5,3,8,2,6,4,3], smooth: true, itemStyle: { color: '#f56c6c' } },
    ]
  }
})
</script>

<style scoped>
.stats-row { margin-bottom: 20px; }
.stat-card { text-align: center; }
.stat-value { font-size: 32px; font-weight: bold; }
.stat-label { font-size: 14px; color: #909399; margin-top: 8px; }
</style>
