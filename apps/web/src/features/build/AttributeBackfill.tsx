import { useEffect, useState } from 'react'

import { apiFetch, type JobSnapshot, type ModelProfile, type ProjectSummary } from '../../api/client'

export function AttributeBackfill({
  project,
  profiles,
  onCreated,
  disabled = false,
}: {
  project?: ProjectSummary
  profiles: ModelProfile[]
  onCreated: (job: JobSnapshot) => void
  disabled?: boolean
}) {
  const [profile, setProfile] = useState(profiles[0]?.id ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const sourceAvailable = project?.source_size != null

  useEffect(() => { if (!profile && profiles[0]) setProfile(profiles[0].id) }, [profile, profiles])

  const submit = async () => {
    if (!project || !profile || !sourceAvailable) return
    setBusy(true)
    setError('')
    try {
      onCreated(await apiFetch<JobSnapshot>(`/api/projects/${project.id}/attribute-jobs`, {
        method: 'POST',
        body: JSON.stringify({ model_profile_id: profile }),
      }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '属性补抽任务创建失败')
    } finally {
      setBusy(false)
    }
  }

  const locked = disabled || busy

  return <section className="attribute-backfill" aria-busy={busy} aria-disabled={disabled}><p className="eyebrow">01B · ATTRIBUTES</p><h2>重新抽取属性</h2><p>对当前项目补抽有原文证据支持的实体属性，不重建实体和关系。</p><label>属性补抽模型<select aria-label="属性补抽模型" value={profile} disabled={locked} onChange={event => setProfile(event.target.value)}>{profiles.map(item => <option key={item.id} value={item.id} disabled={!item.available}>{item.provider} · {item.model}{item.available ? '' : '（不可用）'}</option>)}</select></label>{!sourceAvailable && <p className="empty-note">原始 TXT 不可用</p>}{error && <p role="alert" className="error-state">{error}</p>}<button type="button" className="primary" disabled={locked || !profile || !sourceAvailable} onClick={submit}>{busy ? '正在创建…' : disabled ? '构建处理中' : '重新抽取属性'}</button></section>
}
