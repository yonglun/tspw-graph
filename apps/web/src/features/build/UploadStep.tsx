import { FormEvent, useEffect, useState } from 'react'

import { apiFetch, type ModelProfile, type ProjectCreated } from '../../api/client'

export function UploadStep({ profiles, onCreated, disabled = false }: { profiles: ModelProfile[]; onCreated: (created: ProjectCreated) => void; disabled?: boolean }) {
  const [title, setTitle] = useState('')
  const [file, setFile] = useState<File>()
  const [profile, setProfile] = useState(profiles[0]?.id ?? '')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { if (!profile && profiles[0]) setProfile(profiles[0].id) }, [profile, profiles])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!title.trim()) return setError('请输入项目标题')
    if (!file) return setError('请选择 TXT 小说')
    if (!profile) return setError('请选择模型配置')
    if (file.size > 20 * 1024 * 1024) return setError('文件不能超过 20 MB')
    const body = new FormData()
    body.set('title', title)
    body.set('model_profile_id', profile)
    body.set('file', file)
    setBusy(true)
    setError('')
    try {
      onCreated(await apiFetch<ProjectCreated>('/api/projects/upload', { method: 'POST', body }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '上传失败')
    } finally {
      setBusy(false)
    }
  }

  const locked = disabled || busy

  return <form className="build-upload" onSubmit={submit} noValidate aria-busy={busy} aria-disabled={disabled}>
    <div><p className="eyebrow">01 · SOURCE</p><h2>选择小说文本</h2><p>支持 UTF-8、UTF-8-BOM 与 GB18030，单文件不超过 20 MB。</p></div>
    <label>项目标题<input aria-label="项目标题" value={title} maxLength={300} required disabled={locked} onChange={event => setTitle(event.target.value)} /></label>
    <label>TXT 小说<input aria-label="TXT 小说" type="file" accept=".txt,text/plain" required disabled={locked} onChange={event => setFile(event.target.files?.[0])} /></label>
    <label>模型配置<select aria-label="模型配置" value={profile} required disabled={locked} onChange={event => setProfile(event.target.value)}>{profiles.map(item => <option key={item.id} value={item.id} disabled={!item.available}>{item.provider} · {item.model}{item.available ? '' : '（不可用）'}</option>)}</select></label>
    {error && <p role="alert" className="error-state">{error}</p>}
    <button className="primary" disabled={locked || !profile}>{busy ? '正在上传…' : disabled ? '构建处理中' : '开始构建'}</button>
  </form>
}
