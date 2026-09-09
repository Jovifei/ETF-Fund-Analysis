/** In-process validation only: no URL navigation, network, or production API. */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { makeRouter } from '../src/routerFactory'
import App from '../src/App.vue'
import '../src/style.css'
const router = makeRouter(createMemoryHistory())
Object.assign(window, { validationRouter: router })
void router.push('/')
createApp(App).use(createPinia()).use(router).mount('#app')
