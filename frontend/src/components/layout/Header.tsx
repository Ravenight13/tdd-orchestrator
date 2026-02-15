import { useLocation } from 'react-router-dom'

const TITLES: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/tasks': 'Task Board',
  '/workers': 'Workers',
  '/circuits': 'Circuits',
}

export function Header() {
  const { pathname } = useLocation()
  const title =
    TITLES[pathname] ??
    (pathname.startsWith('/tasks/') ? 'Task Detail' : 'TDD Orchestrator')

  return (
    <header className="flex h-14 items-center border-b border-border px-6">
      <h1 className="text-lg font-semibold">{title}</h1>
    </header>
  )
}
