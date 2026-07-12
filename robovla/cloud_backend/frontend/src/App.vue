<template>
  <div id="app">
    <el-container>
      <el-aside width="220px" v-if="isLoggedIn">
        <SideMenu />
      </el-aside>
      <el-container>
        <el-header v-if="isLoggedIn">
          <HeaderBar />
        </el-header>
        <el-main>
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAuthStore } from './stores/auth'
import SideMenu from './components/SideMenu.vue'
import HeaderBar from './components/HeaderBar.vue'

const authStore = useAuthStore()
const isLoggedIn = computed(() => authStore.isLoggedIn)
</script>

<style>
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
#app { height: 100vh; }
.el-header { background: #2c3e50; padding: 0 20px; display: flex; align-items: center; }
.el-aside { background: #1a252f; min-height: 100vh; }
.el-main { background: #f0f2f5; padding: 20px; }
</style>