<template>
  <div class="license">
    <h2>🔑 授权管理</h2>
    <el-card>
      <template #header>生成新授权码</template>
      <el-form :model="form" label-width="120px">
        <el-form-item label="设备序列号">
          <el-input v-model="form.hardwareSn" placeholder="输入 Jetson 硬件序列号" />
        </el-form-item>
        <el-form-item label="授权类型">
          <el-radio-group v-model="form.authType">
            <el-radio value="trial">试用 (30天)</el-radio>
            <el-radio value="annual">年度 (365天)</el-radio>
            <el-radio value="perpetual">永久买断</el-radio>
            <el-radio value="rental">租赁</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="客户名称">
          <el-input v-model="form.customerName" placeholder="客户/工厂名称" />
        </el-form-item>
        <el-form-item label="联系电话">
          <el-input v-model="form.phone" placeholder="联系电话" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="generate">生成授权码</el-button>
        </el-form-item>
      </el-form>
      <div v-if="generated" style="margin-top: 20px; padding: 16px; background: #f0f9eb">
        <p><strong>序列号:</strong> {{ generated.hardware_sn }}</p>
        <p><strong>授权码:</strong> <code style="font-size: 18px; background:#e8f5e9; padding: 4px 12px">{{ generated.license_code }}</code></p>
        <p><strong>类型:</strong> {{ generated.auth_type }}</p>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import axios from '../api'

const form = reactive({ hardwareSn: '', authType: 'trial', customerName: '', phone: '' })
const generated = ref(null)

const generate = async () => {
  try {
    const res = await axios.post('/api/device/register', form)
    generated.value = { ...res.data, auth_type: form.authType }
  } catch(e) {}
}
</script>