import { useEffect, useState } from 'react'

import { apiFetch, type JobSnapshot } from '../../api/client'
import { StatusDot } from '../../components/StatusDot'

const stages: Record<string, string> = { QUEUED: '等待 Worker', SPLITTING: '识别章节', EXTRACTING: '抽取实体与关系', RESOLVING: '消解实体', VALIDATING: '校验本体与证据', IMPORTING: '写入 Neo4j', COMPLETED: '构建完成', PAUSED: '已暂停', FAILED: '构建失败', CANCELLED: '已取消' }
const attributeStages: Record<string, string> = { ...stages, EXTRACTING: '补抽实体属性', RESOLVING: '匹配已有实体', VALIDATING: '校验属性证据', IMPORTING: '写入属性断言', COMPLETED: '属性补抽完成' }
const terminal = new Set(['COMPLETED', 'FAILED', 'CANCELLED'])

function statusTone(status: string): 'neutral' | 'info' | 'success' | 'warning' | 'error' {
  if (status === 'COMPLETED') return 'success'
  if (status === 'FAILED' || status === 'CANCELLED') return 'error'
  if (status === 'PAUSED') return 'warning'
  if (status === 'QUEUED') return 'neutral'
  return 'info'
}

export function JobProgress({ initial, onChange }: { initial: JobSnapshot; onChange: (job: JobSnapshot) => void }) {
  const [job, setJob] = useState(initial)

  useEffect(() => {
    setJob(initial)
  }, [initial])

  useEffect(() => {
    if (terminal.has(job.status)) return
    let stopped = false
    let pollTimer: number | undefined
    const apply = (next: JobSnapshot) => {
      if (stopped) return
      setJob(next)
      onChange(next)
      if (terminal.has(next.status) && pollTimer) window.clearInterval(pollTimer)
    }
    const poll = () => { apiFetch<JobSnapshot>(`/api/jobs/${job.id}`).then(apply).catch(() => undefined) }
    const startPolling = () => {
      if (pollTimer) return
      poll()
      pollTimer = window.setInterval(poll, 2000)
    }
    const source = new EventSource(`/api/jobs/${job.id}/events`)
    source.addEventListener('job', ((event: MessageEvent) => {
      const next = JSON.parse(event.data) as JobSnapshot
      apply(next)
      if (terminal.has(next.status)) source.close()
    }) as EventListener)
    source.onerror = () => { source.close(); startPolling() }
    return () => { stopped = true; source.close(); if (pollTimer) window.clearInterval(pollTimer) }
  }, [job.id, job.status, onChange])

  const control = async (action: string) => { const next = await apiFetch<JobSnapshot>(`/api/jobs/${job.id}/${action}`, { method: 'POST' }); setJob(next); onChange(next) }
  const percent = job.total_chunks ? Math.round(job.completed_chunks / job.total_chunks * 100) : 0
  const labels = job.kind === 'ATTRIBUTE_BACKFILL' ? attributeStages : stages
  return <section className="job-progress" aria-live="polite"><p className="eyebrow">02 · PIPELINE</p><div className="job-stage"><StatusDot tone={statusTone(job.status)}>{job.status}</StatusDot><h2>{labels[job.status] ?? job.status}</h2></div><progress aria-label="构建进度" max="100" value={percent}>{percent}%</progress><p>{job.completed_chunks} / {job.total_chunks || '待切分'} 个片段</p><div className="job-actions">{!terminal.has(job.status) && job.status !== 'PAUSED' && <button onClick={() => control('pause')}>暂停</button>}{job.status === 'PAUSED' && <button onClick={() => control('resume')}>继续</button>}{!terminal.has(job.status) && <button onClick={() => control('cancel')}>取消</button>}{job.status === 'FAILED' && <button onClick={() => control('retry')}>重试失败片段</button>}</div>{job.error_code && <p role="alert">错误码：{job.error_code}</p>}</section>
}
