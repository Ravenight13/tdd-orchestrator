import { useState, useCallback } from 'react'
import { Upload } from 'lucide-react'

interface PrdUploadZoneProps {
  onContentLoaded: (content: string, filename: string) => void
}

export function PrdUploadZone({ onContentLoaded }: PrdUploadZoneProps) {
  const [dragOver, setDragOver] = useState(false)

  const handleFile = useCallback((file: File) => {
    if (!file.name.endsWith('.md') && !file.name.endsWith('.txt')) {
      return
    }
    const reader = new FileReader()
    reader.onload = (e) => {
      const content = e.target?.result
      if (typeof content === 'string') {
        onContentLoaded(content, file.name)
      }
    }
    reader.readAsText(file)
  }, [onContentLoaded])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }, [handleFile])

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      className={`flex flex-col items-center gap-3 rounded-lg border-2 border-dashed p-8 transition-colors ${
        dragOver ? 'border-primary bg-primary/5' : 'border-border'
      }`}
    >
      <Upload className="size-8 text-muted-foreground" />
      <p className="text-sm text-muted-foreground">
        Drag & drop a <code>.md</code> or <code>.txt</code> file
      </p>
      <label className="cursor-pointer rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90">
        Browse files
        <input
          type="file"
          accept=".md,.txt"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) handleFile(file)
          }}
        />
      </label>
    </div>
  )
}
