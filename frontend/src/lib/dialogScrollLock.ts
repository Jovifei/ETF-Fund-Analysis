const active = new Set<symbol>()

function sync(): void {
  if (typeof document === 'undefined') return
  document.body.classList.toggle('modal-scroll-lock', active.size > 0)
}

export function acquireDialogScrollLock(): symbol {
  const token = Symbol('dialog-scroll-lock')
  active.add(token)
  sync()
  return token
}

export function releaseDialogScrollLock(token: symbol | null | undefined): void {
  if (!token) return
  active.delete(token)
  sync()
}

export function dialogScrollLockCount(): number {
  return active.size
}
