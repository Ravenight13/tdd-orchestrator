export interface NodeLayout {
  id: string
  label: string
  x: number
  y: number
  color: string
}

export interface EdgeLayout {
  from: string
  to: string
  label: string
  path: string
}

const WIDTH = 400
const HEIGHT = 250
const NODE_RADIUS = 35

export function computeCircuitLayout(): { nodes: NodeLayout[]; edges: EdgeLayout[] } {
  // Triangle layout: CLOSED top-left, OPEN top-right, HALF_OPEN bottom-center
  const nodes: NodeLayout[] = [
    { id: 'closed', label: 'CLOSED', x: WIDTH * 0.2, y: HEIGHT * 0.3, color: '#22c55e' },
    { id: 'open', label: 'OPEN', x: WIDTH * 0.8, y: HEIGHT * 0.3, color: '#ef4444' },
    { id: 'half_open', label: 'HALF\nOPEN', x: WIDTH * 0.5, y: HEIGHT * 0.8, color: '#f59e0b' },
  ]

  const nodeMap = new Map(nodes.map((n) => [n.id, n]))

  function edgePath(fromId: string, toId: string, curve: number = 0): string {
    const from = nodeMap.get(fromId)!
    const to = nodeMap.get(toId)!
    const dx = to.x - from.x
    const dy = to.y - from.y
    const dist = Math.sqrt(dx * dx + dy * dy)
    const nx = dx / dist
    const ny = dy / dist
    const sx = from.x + nx * NODE_RADIUS
    const sy = from.y + ny * NODE_RADIUS
    const ex = to.x - nx * NODE_RADIUS
    const ey = to.y - ny * NODE_RADIUS
    if (curve === 0) return `M ${sx} ${sy} L ${ex} ${ey}`
    const mx = (sx + ex) / 2 + ny * curve
    const my = (sy + ey) / 2 - nx * curve
    return `M ${sx} ${sy} Q ${mx} ${my} ${ex} ${ey}`
  }

  const edges: EdgeLayout[] = [
    { from: 'closed', to: 'open', label: 'threshold', path: edgePath('closed', 'open') },
    { from: 'open', to: 'half_open', label: 'timeout', path: edgePath('open', 'half_open') },
    { from: 'half_open', to: 'closed', label: 'success', path: edgePath('half_open', 'closed') },
    { from: 'half_open', to: 'open', label: 'failure', path: edgePath('half_open', 'open', 30) },
  ]

  return { nodes, edges }
}
