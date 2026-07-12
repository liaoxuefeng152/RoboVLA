<template>
  <div class="devices">
    <h2>🖥️ 设备集群监控</h2>
    <el-card>
      <el-table :data="devices" stripe v-loading="loading">
        <el-table-column prop="hardwareSn" label="序列号" width="150" />
        <el-table-column prop="deviceName" label="设备名称" />
        <el-table-column prop="authType" label="授权类型">
          <template #default="{ row }">
            <el-tag :type="row.authType === 'perpetual' ? 'success' : 'warning'">
              {{ { perpetual:'永久', annual:'年度', trial:'试用', rental:'租赁' }[row.authType] || row.authType }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <span :style="{ color: row.status === 'online' ? '#67c23a' : '#909399' }">
              {{ row.status === 'online' ? '🟢 在线' : '⚪ 离线' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="totalProduction" label="产量" width="100" />
        <el-table-column prop="faultCount" label="故障" width="80" />
        <el-table-column prop="lastHeartbeat" label="最后心跳" width="180" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="requestRemote(row)">远程运维</el-button>
            <el-button size="small" type="danger" @click="lockDevice(row)">锁定</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import axios from '../api'

const devices = ref([])
const loading = ref(true)

onMounted(async () => {
  try {
    const res = await axios.get('/api/device/cluster')
    devices.value = res.data?.data?.devices || []
  } catch(e) {
    console.warn('设备 API 未连接')
  } finally {
    loading.value = false
  }
})

const requestRemote = (device) => {
  ElMessage.info(`已向设备 ${device.hardwareSn?.slice(-6)} 发送远程运维请求，等待客户授权`)
}

const lockDevice = (device) => {
  ElMessage.warning(`设备 ${device.hardwareSn?.slice(-6)} 已锁定`)
}
</script>
