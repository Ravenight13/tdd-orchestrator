import { useMemo } from 'react'
import { computeCircuitLayout } from './circuit-layout'
import type { CircuitState } from '@/types/domain'

interface CircuitStateMachineProps {
  currentState: CircuitState
}

export function CircuitStateMachine({ currentState }: CircuitStateMachineProps) {
  const { nodes, edges } = useMemo(() => computeCircuitLayout(), [])

  return (
    <svg viewBox="0 0 400 250" className="w-full max-w-md">
      <defs>
        <marker
          id="arrowhead"
          markerWidth="10"
          markerHeight="7"
          refX="10"
          refY="3.5"
          orient="auto"
          fill="currentColor"
          className="text-muted-foreground"
        >
          <polygon points="0 0, 10 3.5, 0 7" />
        </marker>
      </defs>

      {/* Edges */}
      {edges.map((edge) => (
        <g key={`${edge.from}-${edge.to}`}>
          <path
            d={edge.path}
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            markerEnd="url(#arrowhead)"
            className="text-muted-foreground"
          />
          <text
            className="fill-muted-foreground text-[10px]"
            textAnchor="middle"
          >
            <textPath
              href={`#edge-path-${edge.from}-${edge.to}`}
              startOffset="50%"
            >
              {edge.label}
            </textPath>
          </text>
          <path id={`edge-path-${edge.from}-${edge.to}`} d={edge.path} fill="none" stroke="none" />
        </g>
      ))}

      {/* Nodes */}
      {nodes.map((node) => {
        const isActive = node.id === currentState
        return (
          <g key={node.id}>
            {/* Glow ring for active state */}
            {isActive && (
              <circle
                cx={node.x}
                cy={node.y}
                r={40}
                fill="none"
                stroke={node.color}
                strokeWidth={2}
                opacity={0.4}
                className="animate-pulse"
              />
            )}
            <circle
              cx={node.x}
              cy={node.y}
              r={35}
              fill={isActive ? node.color : 'currentColor'}
              fillOpacity={isActive ? 0.15 : 0.05}
              stroke={node.color}
              strokeWidth={isActive ? 2.5 : 1.5}
              className={isActive ? '' : 'text-muted'}
            />
            {node.label.includes('\n') ? (
              node.label.split('\n').map((line, i) => (
                <text
                  key={i}
                  x={node.x}
                  y={node.y + (i - 0.5) * 14}
                  textAnchor="middle"
                  dominantBaseline="central"
                  className="fill-foreground text-[11px] font-semibold"
                >
                  {line}
                </text>
              ))
            ) : (
              <text
                x={node.x}
                y={node.y}
                textAnchor="middle"
                dominantBaseline="central"
                className="fill-foreground text-[11px] font-semibold"
              >
                {node.label}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}
