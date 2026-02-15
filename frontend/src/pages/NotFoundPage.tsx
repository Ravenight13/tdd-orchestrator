import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-20">
      <h2 className="text-4xl font-bold">404</h2>
      <p className="text-muted-foreground">Page not found</p>
      <Link
        to="/dashboard"
        className="text-sm text-primary underline underline-offset-4"
      >
        Back to Dashboard
      </Link>
    </div>
  )
}
