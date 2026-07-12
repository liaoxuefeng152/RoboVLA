import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('robovla_token') || '')
  const isLoggedIn = computed(() => !!token.value)

  return { token, isLoggedIn }
})
