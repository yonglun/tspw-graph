import { type FormEvent, useState } from 'react'

type AdminDialogProps = {
  title: string
  username?: string
  needsPassword?: boolean
  onClose: () => void
  onSubmit: (username: string, password: string) => Promise<void>
}

export function AdminDialog({
  title,
  username = '',
  needsPassword = false,
  onClose,
  onSubmit,
}: AdminDialogProps) {
  const [name, setName] = useState(username)
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await onSubmit(name, password)
      onClose()
    } catch {
      setError('操作失败，请检查输入后重试。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="admin-dialog" role="dialog" aria-modal="true" aria-label={title}>
        <h2>{title}</h2>
        <form className="auth-form" onSubmit={submit}>
          <label>
            用户名
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={needsPassword && Boolean(username)}
              required={!needsPassword || !username}
              minLength={3}
              maxLength={64}
            />
          </label>
          {needsPassword && (
            <label>
              临时密码
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={10}
                maxLength={1024}
                aria-describedby="temporary-password-hint"
              />
              <small id="temporary-password-hint">至少 10 位，并包含大小写字母、数字和特殊字符。</small>
            </label>
          )}
          {error && <p className="form-error" role="alert">{error}</p>}
          <div className="dialog-actions">
            <button type="button" onClick={onClose}>取消</button>
            <button className="primary" disabled={busy}>确认</button>
          </div>
        </form>
      </section>
    </div>
  )
}
