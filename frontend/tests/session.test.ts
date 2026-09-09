import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, it, expect, vi } from 'vitest'
import { useSession } from '../src/stores/session'
import { api } from '../src/lib/api'
vi.mock('../src/lib/api',()=>({api:vi.fn(),abortAllRequests:vi.fn(),errorText:()=> 'error'}))
beforeEach(()=>{setActivePinia(createPinia());vi.clearAllMocks()})
it('does not resurrect a user after session clear',async()=>{
 let release!: (value: unknown)=>void
 vi.mocked(api).mockImplementation(()=>new Promise(resolve=>{release=resolve}))
 const session=useSession();const pending=session.load();session.clear()
 release({authenticated:true,identifier:'previous-user',role:'member'})
 await pending
 expect(session.authenticated).toBe(false);expect(session.identifier).toBeNull()
})
it('newer load wins when auth responses arrive out of order',async()=>{
 const resolves:((value:unknown)=>void)[]=[]
 vi.mocked(api).mockImplementation(()=>new Promise(resolve=>{resolves.push(resolve)}))
 const session=useSession();const first=session.load(),second=session.load()
 resolves[1]({authenticated:true,identifier:'current-user',role:'member'});await second
 resolves[0]({authenticated:true,identifier:'older-user',role:'admin'});await first
 expect(session.identifier).toBe('current-user');expect(session.role).toBe('member')
})
