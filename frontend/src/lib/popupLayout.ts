/** Viewport geometry only; no chart values or financial calculations. */
export interface PopupAnchor {left:number;right:number;top:number;bottom:number}
export interface PopupViewport {left:number;top:number;width:number;height:number}
export function popupLayout(anchor:PopupAnchor,viewport:PopupViewport,scale=1) {
  if (![anchor.left,anchor.right,anchor.top,anchor.bottom,viewport.left,viewport.top,viewport.width,viewport.height,scale].every(Number.isFinite)||scale<=0||viewport.width<=24||viewport.height<=24) return null
  const margin=12, gap=9
  const leftBound=viewport.left+margin,rightBound=viewport.left+viewport.width-margin
  const topBound=viewport.top+margin,bottomBound=viewport.top+viewport.height-margin
  if(anchor.bottom<topBound||anchor.top>bottomBound||anchor.right<leftBound||anchor.left>rightBound)return null
  const width=Math.min(330*scale,rightBound-leftBound)
  const below=Math.max(0,bottomBound-anchor.bottom-gap),above=Math.max(0,anchor.top-topBound-gap)
  const side=below>=Math.min(360*scale,viewport.height-2*margin)||below>=above?'below':'above'
  const height=Math.min(620*scale,side==='below'?below:above)
  const left=Math.max(leftBound,Math.min(anchor.right-width,rightBound-width))
  const top=side==='below'?anchor.bottom+gap:anchor.top-gap-height
  return {left:(left-anchor.left)/scale,top:(top-anchor.top)/scale,width:width/scale,maxHeight:height/scale,side}
}
