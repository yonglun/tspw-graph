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
  const active = !terminal.has(job.status)
  const preparing = active && job.total_chunks === 0
  const analyzing = preparing && job.status === 'IMPORTING'
  const importing = active && job.total_chunks > 0 && job.completed_chunks >= job.total_chunks
  const extracting = active && job.total_chunks > 0 && job.completed_chunks < job.total_chunks
  const indeterminate = preparing || importing
  const canCancel = active && !importing
  const stageLabel = analyzing
    ? '正在分析文本结构'
    : extracting
      ? `正在抽取第 ${job.completed_chunks + 1} / ${job.total_chunks} 个片段`
      : importing
        ? '正在汇总并写入 Neo4j'
        : labels[job.status] ?? job.status
  const progressCopy = analyzing
    ? '正在识别章节并计算片段总数'
    : importing
      ? `已处理全部 ${job.total_chunks} 个片段，正在生成图谱`
      : job.total_chunks
        ? `已完成 ${job.completed_chunks} / ${job.total_chunks} 个片段`
        : job.status === 'QUEUED'
          ? '等待任务开始'
          : '此阶段尚未产生分片进度'

  return <section className="job-progress" aria-live="polite" aria-busy={active}><p className="eyebrow">02 · PIPELINE</p><div className="job-stage"><StatusDot tone={statusTone(job.status)}>{job.status}</StatusDot><h2>{stageLabel}</h2></div><div className="job-progress-track">{indeterminate ? <progress aria-label="构建进度" max="100">处理中</progress> : <progress aria-label="构建进度" max="100" value={percent}>{percent}%</progress>}</div><p>{progressCopy}</p><div className="job-actions">{canCancel && <button onClick={() => control('cancel')}>取消</button>}{job.status === 'FAILED' && <button onClick={() => control('retry')}>重试失败片段</button>}</div>{importing && <p className="job-progress-note">图谱正在执行最终写入，此阶段不能取消。</p>}{job.error_code && <p role="alert">错误码：{job.error_code}</p>}</section>
}
