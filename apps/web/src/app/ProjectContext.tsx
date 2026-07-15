import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { apiFetch, DEFAULT_PROJECT_ID, type ProjectSummary } from '../api/client'

type ProjectContextValue = { projects: ProjectSummary[]; projectId: string; setProjectId: (id: string) => void; refreshProjects: () => Promise<void> }
const ProjectContext = createContext<ProjectContextValue | undefined>(undefined)
const fallbackProject: ProjectContextValue = { projects: [], projectId: DEFAULT_PROJECT_ID, setProjectId: () => undefined, refreshProjects: async () => undefined }

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [params, setParams] = useSearchParams()
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const requestedProjectId = params.get('project') || DEFAULT_PROJECT_ID
  const userProjects = projects.filter(project => !project.is_builtin)
  const projectId = userProjects.length > 0 && requestedProjectId === DEFAULT_PROJECT_ID ? userProjects[0].id : requestedProjectId
  const refreshProjects = useCallback(async () => {
    const nextProjects = await apiFetch<ProjectSummary[]>('/api/projects')
    setProjects(Array.isArray(nextProjects) ? nextProjects : [])
  }, [])
  useEffect(() => { refreshProjects().catch(() => setProjects([])) }, [refreshProjects])
  const setProjectId = useCallback((id: string) => {
    const next = new URLSearchParams(params)
    next.set('project', id)
    next.delete('entity')
    setParams(next, { replace: true })
  }, [params, setParams])
  useEffect(() => {
    if (projectId === requestedProjectId) return
    setProjectId(projectId)
  }, [projectId, requestedProjectId, setProjectId])
  const value = useMemo(() => ({ projects, projectId, setProjectId, refreshProjects }), [projects, projectId, setProjectId, refreshProjects])
  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>
}

export function useProject() {
  return useContext(ProjectContext) ?? fallbackProject
}
