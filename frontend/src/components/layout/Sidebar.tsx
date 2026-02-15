import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  KanbanSquare,
  Users,
  ShieldCheck,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/tasks', label: 'Tasks', icon: KanbanSquare },
  { to: '/workers', label: 'Workers', icon: Users },
  { to: '/circuits', label: 'Circuits', icon: ShieldCheck },
] as const

export function Sidebar() {
  return (
    <aside className="flex w-56 flex-col border-r border-border bg-muted/40">
      <div className="flex h-14 items-center gap-2 border-b border-border px-4">
        <div className="size-7 rounded-md bg-primary" />
        <span className="text-sm font-semibold tracking-tight">
          TDD Orchestrator
        </span>
      </div>
      <nav className="flex-1 space-y-1 p-3">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
              )
            }
          >
            <Icon className="size-4" />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
