<template>
  <div class="login-container">
    <el-card class="login-card">
      <h2 style="text-align: center; margin-bottom: 24px">RoboVLA 云端管理后台</h2>
      <el-form :model="form">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" prefix-icon="User" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="密码" prefix-icon="Lock" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" style="width: 100%" @click="login">登 录</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

const router = useRouter()
const form = reactive({ username: 'admin', password: '' })

const login = () => {
  if (form.username && form.password) {
    localStorage.setItem('robovla_token', 'demo_token_' + Date.now())
    router.push('/dashboard')
  } else {
    ElMessage.error('请输入用户名和密码')
  }
}
</script>

<style scoped>
.login-container { display: flex; justify-content: center; align-items: center; height: 100vh; background: #1a252f; }
.login-card { width: 400px; }
</style>