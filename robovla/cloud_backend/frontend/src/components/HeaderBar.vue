<template>
  <div class="header-bar">
    <span style="color: white; font-size: 16px;">RoboVLA 工业具身智能管理平台</span>
    <el-button text style="color: white; margin-left: auto" @click="logout">退出登录</el-button>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()
const logout = () => {
  localStorage.removeItem('robovla_token')
  router.push('/login')
}
</script>

<style scoped>
.header-bar { display: flex; width: 100%; align-items: center; }
</style>