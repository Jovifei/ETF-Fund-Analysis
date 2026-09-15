/** Keyboard order only; never target disabled/hidden controls when trapping Tab. */
export function drawerFocusTargets(root: ParentNode): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>('a[href], button, input, select, textarea, [tabindex]'))
    .filter(el => el.offsetParent !== null && el.tabIndex >= 0
      && !el.matches(':disabled, [hidden], [aria-hidden="true"]')
      && !el.closest('[inert], [hidden], [aria-hidden="true"]'))
}
