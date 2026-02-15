import { useMemo } from 'react'
import { useTheme } from '@/hooks/useTheme'

function getCssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export function useChartColors() {
  const { resolvedTheme } = useTheme()

  return useMemo(() => {
    // Force re-read when theme changes
    void resolvedTheme
    return {
      primary: getCssVar('--color-primary'),
      foreground: getCssVar('--color-foreground'),
      muted: getCssVar('--color-muted'),
      mutedForeground: getCssVar('--color-muted-foreground'),
      statusPending: getCssVar('--color-status-pending'),
      statusRunning: getCssVar('--color-status-running'),
      statusPassed: getCssVar('--color-status-passed'),
      statusFailed: getCssVar('--color-status-failed'),
      background: getCssVar('--color-background'),
      card: getCssVar('--color-card'),
      border: getCssVar('--color-border'),
    }
  }, [resolvedTheme])
}
