import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || 'http://localhost:8080',
  timeout: 10000,
})

api.interceptors.request.use(config => {
  const token = localStorage.getItem('robovla_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      localStorage.removeItem('robovla_token')
      window.location.hash = '#/login'
    }
    return Promise.reject(error)
  }
)

export default api
