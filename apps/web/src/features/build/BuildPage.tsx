import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { apiFetch, type JobSnapshot, type ModelProfile, type ProjectCreated, type QualityReport as Report } from '../../api/client'
import { useProject } from '../../app/ProjectContext'
import { AttributeBackfill } from './AttributeBackfill'
import { JobProgress } from './JobProgress'; import { QualityReport } from './QualityReport'; import { UploadStep } from './UploadStep'

export function BuildPage() {
  const [params, setParams] = useSearchParams(); const [profiles, setProfiles] = useState<ModelProfile[]>([]); const [created, setCreated] = useState<ProjectCreated>(); const [report, setReport] = useState<Report>(); const [error, setError] = useState(''); const { projectId, projects, refreshProjects, setProjectSwitchLocked } = useProject()
  const processing = Boolean(created && !['COMPLETED', 'FAILED', 'CANCELLED'].includes(created.job.status))
  useEffect(() => { apiFetch<ModelProfile[]>('/api/model-profiles').then(setProfiles).catch(e => setError(e.message)) }, [])
  useEffect(() => {
    const jobId = params.get('job'); const projectId = params.get('project')
    if (!jobId || !projectId || created) return
    Promise.all([apiFetch<JobSnapshot>(`/api/jobs/${jobId}`), apiFetch<ProjectCreated['project']>(`/api/projects/${projectId}`)])
      .then(([job, project]) => setCreated({ job, project }))
      .catch(e => setError(e instanceof Error ? e.message : '无法恢复构建任务'))
  }, [created, params])
  useEffect(() => {
    setProjectSwitchLocked(processing)
    return () => setProjectSwitchLocked(false)
  }, [processing, setProjectSwitchLocked])
  const onJob = useCallback((job: JobSnapshot) => { setCreated(current => current ? { ...current, job } : current); if (job.status === 'COMPLETED') { apiFetch<Report>(`/api/jobs/${job.id}/quality`).then(setReport).catch(e => setError(e.message)); refreshProjects() } }, [refreshProjects])
  const onCreated = (next: ProjectCreated) => { setCreated(next); setReport(undefined); const nextParams = new URLSearchParams(params); nextParams.set('project', next.project.id); nextParams.set('job', next.job.id); setParams(nextParams, { replace: true }); refreshProjects() }
  const currentProject = projects.find(project => project.id === projectId)
  const onAttributeJob = (job: JobSnapshot) => { if (!currentProject) return; setCreated({ project: currentProject, job }); setReport(undefined); const nextParams = new URLSearchParams(params); nextParams.set('project', currentProject.id); nextParams.set('job', job.id); setParams(nextParams, { replace: true }) }
  return <section className="page build-page"><header className="page-header"><div><p className="eyebrow">ONLINE BUILD · 06</p><h1>从文本，生长出图谱</h1><p>上传一部小说，观察章节、实体、事实与证据如何逐步进入知识图谱。</p></div></header>{error && <p role="alert" className="error-state">{error}</p>}<div className="build-grid"><div className="build-source-stack"><UploadStep profiles={profiles} onCreated={onCreated} disabled={processing} /><AttributeBackfill project={currentProject} profiles={profiles} onCreated={onAttributeJob} disabled={processing} /></div>{created ? <JobProgress initial={created.job} onChange={onJob} /> : <div className="build-placeholder"><span>二</span><p>任务建立后，这里会显示可恢复的抽取进度。</p></div>}{created && report ? <QualityReport report={report} projectId={created.project.id} /> : <div className="build-placeholder"><span>三</span><p>构建结束后展示实体、事实、证据与拒绝原因。</p></div>}</div></section>
}
