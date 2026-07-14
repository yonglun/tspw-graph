import { useCallback, useEffect, useState } from 'react'

import { apiFetch } from '../../api/client'
import type { AdminSummary } from '../../app/AuthContext'
import { useAuth } from '../../app/AuthContext'
import { AdminDialog } from './AdminDialog'

type Audit = { id: string; actor_username?: string; target_username?: string; action: string; result: string; created_at: string }

export function AdminPage() {
  const auth = useAuth(); const [admins, setAdmins] = useState<AdminSummary[]>([]); const [audit, setAudit] = useState<Audit[]>([]); const [dialog, setDialog] = useState<{ mode: 'create' | 'rename' | 'reset'; admin?: AdminSummary }>()
  const load = useCallback(async () => { const [accounts, events] = await Promise.all([apiFetch<AdminSummary[]>('/api/admins'), apiFetch<{ items: Audit[] }>('/api/admin-audit-events?limit=30')]); setAdmins(accounts); setAudit(events.items) }, [])
  useEffect(() => { void load() }, [load])
  async function action(path: string) { await apiFetch(path, { method: 'POST' }); await load() }
  return <section className="page admin-page"><header className="page-header"><div><p className="eyebrow">ADMINISTRATION · 10</p><h1>管理员与安全审计</h1><p>维护可访问构建和审核能力的管理员账户。</p></div><button className="primary" onClick={() => setDialog({ mode: 'create' })}>新增管理员</button></header><div className="admin-layout"><section className="surface"><h2>管理员</h2><div className="admin-table">{admins.map(item => <article key={item.id}><span className={`status-dot ${item.is_enabled ? 'success' : 'muted'}`} /><div><b>{item.username}</b><small>{item.must_change_password ? '登录后须修改密码' : '密码状态正常'}</small></div><div className="row-actions"><button onClick={() => setDialog({ mode: 'rename', admin: item })}>改名</button><button onClick={() => setDialog({ mode: 'reset', admin: item })}>重置密码</button>{item.id !== auth.admin?.id && <button onClick={() => action(`/api/admins/${item.id}/${item.is_enabled ? 'disable' : 'enable'}`)}>{item.is_enabled ? '停用' : '启用'}</button>}</div></article>)}</div></section><section className="surface"><h2>最近审计</h2><ol className="audit-list">{audit.map(item => <li key={item.id}><span className={`status-dot ${item.result === 'SUCCESS' ? 'success' : 'danger'}`} /><div><b>{item.action}</b><small>{item.actor_username ?? 'system'} → {item.target_username ?? '—'} · {new Date(item.created_at).toLocaleString()}</small></div></li>)}</ol></section></div>{dialog && <AdminDialog title={dialog.mode === 'create' ? '新增管理员' : dialog.mode === 'rename' ? '修改用户名' : '重置临时密码'} username={dialog.admin?.username} needsPassword={dialog.mode !== 'rename'} onClose={() => setDialog(undefined)} onSubmit={async (username, password) => { if (dialog.mode === 'create') await apiFetch('/api/admins', { method: 'POST', body: JSON.stringify({ username, temporary_password: password }) }); else if (dialog.mode === 'rename') await apiFetch(`/api/admins/${dialog.admin!.id}`, { method: 'PATCH', body: JSON.stringify({ username }) }); else await apiFetch(`/api/admins/${dialog.admin!.id}/reset-password`, { method: 'POST', body: JSON.stringify({ temporary_password: password }) }); await load() }} />}</section>
}
