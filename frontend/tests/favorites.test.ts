import {createPinia,setActivePinia} from 'pinia'
import {beforeEach,it,expect,vi} from 'vitest'
import {useFavorites} from '../src/stores/favorites'
import {useSession} from '../src/stores/session'
import {api} from '../src/lib/api'
vi.mock('../src/lib/api',()=>({api:vi.fn(),abortAllRequests:vi.fn(),errorText:()=> 'error'}))
beforeEach(()=>{setActivePinia(createPinia());vi.clearAllMocks()})
it('deduplicates initial reads and toggles the existing user entry, not a new holding',async()=>{
 let items:{ts_code:string;id:number}[]=[]
 vi.mocked(api).mockImplementation(async(url,opts)=>{
  if(opts?.method==='POST'){items=[{ts_code:'512480.SH',id:7}];return {status:'ok'} as never}
  if(opts?.method==='DELETE'){items=[];return {status:'ok'} as never}
  return {items} as never
 })
 const store=useFavorites();await Promise.all([store.ensure(),store.ensure()]);expect(api).toHaveBeenCalledTimes(1)
 await store.toggle('512480.SH');expect(store.entries['512480.SH']).toBe(7)
 await store.toggle('512480.SH');expect(store.entries['512480.SH']).toBeUndefined()
 expect(api).toHaveBeenCalledWith('/api/watchlist/entries/7',{method:'DELETE'})
})
it('ignores a previous user watchlist response after logout',async()=>{
 let release!:(x:unknown)=>void
 vi.mocked(api).mockImplementation(()=>new Promise(resolve=>{release=resolve}))
 const store=useFavorites(),session=useSession(),pending=store.ensure()
 session.clear();release({items:[{id:99,ts_code:'512480.SH'}]});await pending
 expect(store.entries).toEqual({});expect(store.loaded).toBe(false)
})
