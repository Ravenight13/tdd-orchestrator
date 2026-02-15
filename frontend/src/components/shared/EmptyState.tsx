import type { LucideIcon } from 'lucide-react'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description?: string
}

export function EmptyState({ icon: Icon, title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
      <Icon className="size-10 text-muted-foreground/50" />
      <div>
        <p className="font-medium text-muted-foreground">{title}</p>
        {description && (
          <p className="mt-1 text-sm text-muted-foreground/70">{description}</p>
        )}
      </div>
    </div>
  )
}
