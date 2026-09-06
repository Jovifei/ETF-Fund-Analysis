import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import App from '../src/App.vue'
vi.mock('../src/lib/api', () => ({ api: vi.fn(async (path: string) => path === '/api/auth/me' ? {authenticated:true,identifier:null,role:null} : {market_provider:'mock'}), abortAllRequests: vi.fn(), errorText: () => 'error' }))
describe('bootstrap branch transition', () => {
  it('replaces the loading branch without duplicate keyed block identity', async () => {
    const router = createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{template:'<h1>Ready</h1>'}}]})
    await router.push('/'); await router.isReady()
    const wrapper=mount(App,{global:{plugins:[createPinia(),router]}})
    await flushPromises()
    expect(wrapper.find('.workspace').exists()).toBe(true)
    expect(wrapper.find('.boot-state').exists()).toBe(false)
    expect(wrapper.text()).toContain('Ready')
    wrapper.unmount()
  })
})
