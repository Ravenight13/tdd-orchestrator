import { useState } from 'react'

interface PrdConfigFormProps {
  defaultName: string
  onSubmit: (config: {
    name: string
    workers: number
    dry_run: boolean
    create_pr: boolean
  }) => void
  submitting: boolean
}

export function PrdConfigForm({ defaultName, onSubmit, submitting }: PrdConfigFormProps) {
  const [name, setName] = useState(defaultName)
  const [workers, setWorkers] = useState(2)
  const [dryRun, setDryRun] = useState(false)
  const [createPr, setCreatePr] = useState(false)

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit({ name, workers, dry_run: dryRun, create_pr: createPr })
      }}
      className="space-y-4"
    >
      <div>
        <label className="mb-1 block text-sm font-medium">Project Name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          required
        />
      </div>
      <div>
        <label className="mb-1 block text-sm font-medium">Workers</label>
        <input
          type="number"
          value={workers}
          onChange={(e) => setWorkers(Number(e.target.value))}
          min={1}
          max={8}
          className="w-24 rounded-md border border-input bg-background px-3 py-2 text-sm"
        />
      </div>
      <div className="flex gap-4">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={dryRun}
            onChange={(e) => setDryRun(e.target.checked)}
            className="rounded"
          />
          Dry run
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={createPr}
            onChange={(e) => setCreatePr(e.target.checked)}
            className="rounded"
          />
          Create PR
        </label>
      </div>
      <button
        type="submit"
        disabled={submitting || !name.trim()}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
      >
        {submitting ? 'Submitting...' : 'Submit PRD'}
      </button>
    </form>
  )
}
