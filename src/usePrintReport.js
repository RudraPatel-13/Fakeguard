import { useAuth } from './context/authContext.js'
import { useApp } from './appContext.js'

/** Print / PDF export is a members feature: guests are prompted to sign in. */
export function usePrintReport() {
  const { isAuthenticated, openAuth } = useAuth()
  const { toast } = useApp()
  const printReport = () => {
    if (isAuthenticated) return window.print()
    toast('Sign in to export PDF audit reports.', 'warn')
    openAuth('login')
  }
  return { isAuthenticated, printReport }
}
