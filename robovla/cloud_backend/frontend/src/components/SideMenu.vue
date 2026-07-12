<template>
  <div class="side-menu">
    <div class="logo">🤖 RoboVLA SaaS</div>
    <el-menu :default-active="currentRoute" background-color="#1a252f" text-color="#bfcbd9" active-text-color="#409eff" router>
      <el-menu-item index="/dashboard">
        <el-icon><DataAnalysis /></el-icon><span>仪表盘</span>
      </el-menu-item>
      <el-menu-item index="/devices">
        <el-icon><Monitor /></el-icon><span>设备监控</span>
      </el-menu-item>
      <el-menu-item index="/reports">
        <el-icon><Document /></el-icon><span>生产报表</span>
      </el-menu-item>
      <el-menu-item index="/license">
        <el-icon><Key /></el-icon><span>授权管理</span>
      </el-menu-item>
      <el-menu-item index="/settings">
        <el-icon><Setting /></el-icon><span>系统设置</span>
      </el-menu-item>
    </el-menu>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const currentRoute = computed(() => route.path)
</script>

<style scoped>
.logo { color: #409eff; font-size: 16px; font-weight: bold; padding: 20px 16px; text-align: center; border-bottom: 1px solid #2c3e50; }
</style>