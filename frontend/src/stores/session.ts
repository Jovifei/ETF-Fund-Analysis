import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, abortAllRequests, errorText } from '../lib/api'
export const useSession = defineStore('session', () => {
  const ready = ref(false), authenticated = ref(false), identifier = ref<string | null>(null), role = ref<string | null>(null), error = ref(''), generation = ref(0)
  function clear() { abortAllRequests(); authenticated.value = false; identifier.value = null; role.value = null; generation.value++ }
  async function load() { try { const value = await api<{ authenticated: boolean; identifier: string | null; role: string | null }>('/api/auth/me'); authenticated.value = value.authenticated; identifier.value = value.identifier; role.value = value.role } catch (e) { clear(); error.value = errorText(e) } finally { ready.value = true } }
  async function login(identifierInput: string, password: string) { error.value = ''; await api('/api/auth/login', { method: 'POST', body: { identifier: identifierInput, password } }); generation.value++; await load() }
  async function logout() { await api('/api/auth/logout', { method: 'POST' }); clear() }
  return { ready, authenticated, identifier, role, error, generation, clear, load, login, logout }
})
