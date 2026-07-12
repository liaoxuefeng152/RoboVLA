<template>
  <div class="reports">
    <h2>📊 生产报表</h2>
    <el-card>
      <el-form :inline="true">
        <el-form-item label="日期">
          <el-date-picker v-model="date" type="date" placeholder="选择日期" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadReport">查询</el-button>
          <el-button type="success" @click="exportExcel">导出 Excel</el-button>
        </el-form-item>
      </el-form>
      <el-divider />

      <div v-if="report" v-loading="loading" class="report-stats">
        <el-row :gutter="20">
          <el-col :span="4" v-for="item in reportItems" :key="item.label">
            <el-statistic :title="item.label" :value="item.value" />
          </el-col>
        </el-row>

        <el-row :gutter="20" style="margin-top: 24px">
          <el-col :span="16">
            <el-card>
              <template #header>📈 产量趋势</template>
              <v-chart :option="chartOption" style="height: 300px" autoresize />
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card>
              <template #header>⚠️ 不良原因 TOP5</template>
              <el-table :data="defectReasons" size="small" border>
                <el-table-column prop="reason" label="原因" />
                <el-table-column prop="count" label="次数" width="80" />
              </el-table>
            </el-card>
          </el-col>
        </el-row>

        <el-row style="margin-top: 20px">
          <el-col :span="24">
            <el-card>
              <template #header>📝 生产明细</template>
              <el-table :data="details" size="small" border>
                <el-table-column prop="time" label="时间" width="80" />
                <el-table-column prop="cycle" label="循环号" width="80" />
                <el-table-column prop="sku" label="SKU" />
                <el-table-column prop="status" label="状态" width="90">
                  <template #default="scope">
                    <el-tag :type="scope.row.status === '良品' ? 'success' : 'danger'">{{ scope.row.status }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="duration" label="耗时" width="80" />
              </el-table>
            </el-card>
          </el-col>
        </el-row>
      </div>
      <el-empty v-else description="点击「查询」加载报表数据" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import dayjs from 'dayjs'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import axios from '../api'

use([CanvasRenderer, LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent])

const date = ref(new Date())
const report = ref(null)
const loading = ref(false)
const chartOption = ref({})
const defectReasons = ref([])
const details = ref([])

const reportItems = ref([])

const loadReport = async () => {
  loading.value = true
  const d = dayjs(date.value).format('YYYY-MM-DD')
  try {
    const res = await axios.get('/api/report/daily', { params: { date: d } })
    const r = res.data?.data || {}
    report.value = r
    reportItems.value = [
      { label: '生产循环', value: (r.totalCycles ?? '-').toLocaleString() },
      { label: '良品数', value: (r.goodCount ?? '-').toLocaleString() },
      { label: '不良数', value: (r.badCount ?? '-').toLocaleString() },
      { label: '良率', value: (r.yieldRate ?? '-') + '%' },
      { label: '运行时长', value: (r.durationHours ?? '-') + 'h' },
      { label: '错误次数', value: r.errors ?? '-' },
    ]

    if (r.trend) {
      chartOption.value = {
        tooltip: { trigger: 'axis' },
        legend: { data: ['良品', '不良'] },
        xAxis: { type: 'category', data: r.trend.hours },
        yAxis: { type: 'value' },
        series: [
          { name: '良品', type: 'line', data: r.trend.good, smooth: true, itemStyle: { color: '#67c23a' } },
          { name: '不良', type: 'bar', data: r.trend.bad, itemStyle: { color: '#f56c6c' } },
        ],
      }
    }
    defectReasons.value = r.defectReasons || []
    details.value = r.details || []
  } catch(e) {
    console.warn('报表 API 未连接')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadReport()
})

const exportExcel = async () => {
  try {
    const res = await axios.get('/api/report/export', { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `报表_${dayjs(date.value).format('YYYYMMDD')}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  } catch(e) {
    console.warn('导出失败')
  }
}
</script>

<style scoped>
.report-stats { margin-top: 8px; }
</style>
