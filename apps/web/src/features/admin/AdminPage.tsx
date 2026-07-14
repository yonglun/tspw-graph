import { useCallback, useEffect, useState } from 'react'

import { ApiError, apiFetch } from '../../api/client'
import type { AdminSummary } from '../../app/AuthContext'
import { useAuth } from '../../app/AuthContext'
import { AdminDialog } from './AdminDialog'

type Audit = {
  id: string
  actor_username?: string
  target_username?: string
  action: string
  result: string
  created_at: string
}

type DialogState = { mode: 'create' | 'rename' | 'reset'; admin?: AdminSummary }

function operationError(error: unknown) {
  if (error instanceof ApiError) return `操作失败：${error.code}`
  return '操作失败，请稍后重试。'
}

export function AdminPage() {
  const auth = useAuth()
  const [admins, setAdmins] = useState<AdminSummary[]>([])
  const [audit, setAudit] = useState<Audit[]>([])
  const [dialog, setDialog] = useState<DialogState>()
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [accounts, events] = await Promise.all([
        apiFetch<AdminSummary[]>('/api/admins'),
        apiFetch<{ items: Audit[] }>('/api/admin-audit-events?limit=30'),
      ])
      setAdmins(accounts)
      setAudit(events.items)
      setError('')
    } catch (loadError) {
      setError(operationError(loadError))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function action(path: string) {
    try {
      await apiFetch(path, { method: 'POST' })
      await load()
    } catch (actionError) {
      setError(operationError(actionError))
    }
  }

  const enabledCount = admins.filter((item) => item.is_enabled).length

  return (
    <section className="page admin-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ADMINISTRATION · 10</p>
          <h1>管理员与安全审计</h1>
          <p>维护可访问构建和审核能力的管理员账户。</p>
        </div>
        <button className="primary" onClick={() => setDialog({ mode: 'create' })}>
          新增管理员
        </button>
      </header>

      {error && <p className="form-error admin-error" role="alert">{error}</p>}

      <div className="admin-layout">
        <section className="surface">
          <h2>管理员</h2>
          <div className="admin-table">
            {admins.map((item) => {
              const isSelf = item.id === auth.admin?.id
              const isLastEnabled = item.is_enabled && enabledCount <= 1
              const disableReason = isSelf
                ? '不能停用当前登录账号'
                : isLastEnabled
                  ? '系统必须至少保留一个启用的管理员'
                  : undefined
              return (
                <article key={item.id}>
                  <span className={`status-dot ${item.is_enabled ? 'success' : 'muted'}`} />
                  <div>
                    <b>{item.username}</b>
                    <small>
                      {item.must_change_password ? '登录后须修改密码' : '密码状态正常'}
                      {' · '}
                      更新于 {new Date(item.updated_at).toLocaleString()}
                    </small>
                  </div>
                  <div className="row-actions">
                    <button aria-label={`修改 ${item.username} 用户名`} onClick={() => setDialog({ mode: 'rename', admin: item })}>改名</button>
                    <button aria-label={`重置 ${item.username} 密码`} onClick={() => setDialog({ mode: 'reset', admin: item })}>重置密码</button>
                    {item.is_enabled ? (
                      <button
                        aria-label={`停用 ${item.username}`}
                        disabled={Boolean(disableReason)}
                        title={disableReason}
                        onClick={() => void action(`/api/admins/${item.id}/disable`)}
                      >
                        停用
                      </button>
                    ) : (
                      <button aria-label={`启用 ${item.username}`} onClick={() => void action(`/api/admins/${item.id}/enable`)}>启用</button>
                    )}
                  </div>
                </article>
              )
            })}
          </div>
        </section>

        <section className="surface">
          <h2>最近审计</h2>
          <ol className="audit-list">
            {audit.map((item) => (
              <li key={item.id}>
                <span className={`status-dot ${item.result === 'SUCCESS' ? 'success' : 'danger'}`} />
                <div>
                  <b>{item.action}</b>
                  <small>{item.actor_username ?? 'system'} → {item.target_username ?? '—'} · {new Date(item.created_at).toLocaleString()}</small>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>

      {dialog && (
        <AdminDialog
          title={dialog.mode === 'create' ? '新增管理员' : dialog.mode === 'rename' ? '修改用户名' : '重置临时密码'}
          username={dialog.admin?.username}
          needsPassword={dialog.mode !== 'rename'}
          onClose={() => setDialog(undefined)}
          onSubmit={async (username, password) => {
            if (dialog.mode === 'create') {
              await apiFetch('/api/admins', { method: 'POST', body: JSON.stringify({ username, temporary_password: password }) })
            } else if (dialog.mode === 'rename') {
              await apiFetch(`/api/admins/${dialog.admin!.id}`, { method: 'PATCH', body: JSON.stringify({ username }) })
            } else {
              await apiFetch(`/api/admins/${dialog.admin!.id}/reset-password`, { method: 'POST', body: JSON.stringify({ temporary_password: password }) })
            }
            await load()
          }}
        />
      )}
    </section>
  )
}
