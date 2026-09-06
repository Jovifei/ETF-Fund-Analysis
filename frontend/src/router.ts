import { createWebHistory } from 'vue-router'
import { makeRouter } from './routerFactory'
export { makeRouter, etfPath } from './routerFactory'
export const router = makeRouter(createWebHistory())
