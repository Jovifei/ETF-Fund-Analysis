import { afterEach, describe, expect, it } from 'vitest'
import { drawerFocusTargets } from '../src/lib/navigationFocus'

afterEach(() => document.body.replaceChildren())
function fixture() {
  const root=document.createElement('aside')
  root.innerHTML='<a href="/">Home</a><button>Close</button><button disabled>Logout</button><button hidden>Hidden</button><button tabindex="-1">Skip</button>'
  document.body.append(root)
  for(const el of root.querySelectorAll('a,button')) Object.defineProperty(el,'offsetParent',{get:()=>el.hasAttribute('hidden')?null:root})
  return root
}
describe('drawer keyboard targets',()=>{
  it('excludes a disabled last button instead of letting Tab escape the dialog',()=>{
    const targets=drawerFocusTargets(fixture())
    expect(targets.map(el=>el.textContent)).toEqual(['Home','Close'])
  })
  it('excludes aria-hidden targets and returns no candidates for empty drawer',()=>{
    const root=fixture();root.querySelector('a')!.setAttribute('aria-hidden','true')
    expect(drawerFocusTargets(root).map(el=>el.textContent)).toEqual(['Close'])
    root.replaceChildren();expect(drawerFocusTargets(root)).toEqual([])
  })
})
