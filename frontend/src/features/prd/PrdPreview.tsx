interface PrdPreviewProps {
  content: string
  filename: string
}

export function PrdPreview({ content, filename }: PrdPreviewProps) {
  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <span className="text-xs font-medium text-muted-foreground">{filename}</span>
        <span className="text-xs text-muted-foreground">
          {content.length.toLocaleString()} chars
        </span>
      </div>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap p-4 font-mono text-xs leading-relaxed">
        {content}
      </pre>
    </div>
  )
}
