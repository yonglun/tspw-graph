import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  apiFetch,
  getTimelineDetail,
  type EntitySummary,
  type TimelineEventDetail,
  type TimelineRelationship,
} from '../../api/client'
import { useProject } from '../../app/ProjectContext'

type TimelineItem = { event: EntitySummary; chapter_number?: number }
type RelationshipStateGroupProps = {
  title: string
  tone: 'started' | 'active' | 'ended'
  items: TimelineRelationship[]
  emptyText: string
}

function chapterRange(item: TimelineRelationship) {
  if (item.from_chapter && item.to_chapter) return `第 ${item.from_chapter}–${item.to_chapter} 章`
  if (item.from_chapter) return `始于第 ${item.from_chapter} 章`
  if (item.to_chapter) return `结束于第 ${item.to_chapter} 章`
  return ''
}

function RelationshipStateGroup({ title, tone, items, emptyText }: RelationshipStateGroupProps) {
  return (
    <section className="timeline-state-card" aria-label={title}>
      <h3><span className={`timeline-state-dot is-${tone}`} aria-hidden="true" />{title}</h3>
      {items.length ? (
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <p>{item.source.name} <span aria-label="关系">{item.label}</span> {item.target.name}</p>
              {chapterRange(item) && <small>{chapterRange(item)}</small>}
            </li>
          ))}
        </ul>
      ) : <p className="timeline-state-empty">{emptyText}</p>}
    </section>
  )
}

function EventDetail({ detail, onViewGraph }: { detail: TimelineEventDetail; onViewGraph: () => void }) {
  return (
    <div className="timeline-event-detail">
      <section className="timeline-detail-section" aria-labelledby={`participants-${detail.event.id}`}>
        <h3 id={`participants-${detail.event.id}`}>参与人物</h3>
        <div className="timeline-participants">
          {detail.participants.length
            ? detail.participants.map((participant) => <span key={participant.id}>{participant.name}</span>)
            : <p className="timeline-state-empty">暂无参与人物记录</p>}
        </div>
      </section>
      {detail.chapter_number ? (
        <div className="timeline-state-grid">
          <RelationshipStateGroup title="新增关系" tone="started" items={detail.relationship_states.started} emptyText="本章无新增关系" />
          <RelationshipStateGroup title="持续关系" tone="active" items={detail.relationship_states.active} emptyText="本章无持续关系" />
          <RelationshipStateGroup title="结束关系" tone="ended" items={detail.relationship_states.ended} emptyText="本章无结束关系" />
        </div>
      ) : <p className="timeline-state-notice">该事件缺少章节信息，暂不推断关系状态。</p>}
      <section className="timeline-evidence" aria-labelledby={`evidence-${detail.event.id}`}>
        <h3 id={`evidence-${detail.event.id}`}>原文证据</h3>
        {detail.evidence.length ? detail.evidence.map((evidence) => (
          <blockquote key={evidence.id}>
            <p>{evidence.quote}</p>
            <footer>第 {evidence.chapter_number} 章{evidence.chapter_title ? ` · ${evidence.chapter_title}` : ''}</footer>
          </blockquote>
        )) : <p className="timeline-state-empty">暂无原文证据</p>}
      </section>
      <div className="timeline-detail-actions">
        <button type="button" onClick={onViewGraph}>在图谱中查看</button>
      </div>
    </div>
  )
}

function errorMessage(error: unknown) {
  if (error instanceof Error && error.message) return error.message
  return '请稍后重试'
}

export function StoryPage() {
  const { projectId } = useProject()
  const navigate = useNavigate()
  const [people, setPeople] = useState<EntitySummary[]>([])
  const [person, setPerson] = useState('')
  const [events, setEvents] = useState<TimelineItem[]>([])
  const [expandedId, setExpandedId] = useState<string>()
  const [details, setDetails] = useState<Record<string, TimelineEventDetail>>({})
  const [detailLoading, setDetailLoading] = useState<string>()
  const [detailErrors, setDetailErrors] = useState<Record<string, string>>({})
  const detailRequest = useRef<AbortController | undefined>(undefined)

  useEffect(() => {
    setPerson('')
    setExpandedId(undefined)
    setDetails({})
    detailRequest.current?.abort()
    apiFetch<EntitySummary[]>(`/api/graph/search?project_id=${projectId}&query=${encodeURIComponent('令狐')}&types=Person`).then(setPeople).catch(() => setPeople([]))
  }, [projectId])

  useEffect(() => {
    setExpandedId(undefined)
    detailRequest.current?.abort()
    const suffix = person ? `&person_id=${encodeURIComponent(person)}` : ''
    apiFetch<TimelineItem[]>(`/api/graph/timeline?project_id=${projectId}${suffix}`).then(setEvents).catch(() => setEvents([]))
  }, [person, projectId])

  useEffect(() => () => detailRequest.current?.abort(), [])

  async function toggleEvent(eventId: string, forceReload = false) {
    if (!forceReload && expandedId === eventId) {
      setExpandedId(undefined)
      return
    }
    setExpandedId(eventId)
    if (!forceReload && details[eventId]) return

    detailRequest.current?.abort()
    const controller = new AbortController()
    detailRequest.current = controller
    setDetailLoading(eventId)
    setDetailErrors((current) => ({ ...current, [eventId]: '' }))
    try {
      const detail = await getTimelineDetail(projectId, eventId, controller.signal)
      if (!controller.signal.aborted) setDetails((current) => ({ ...current, [eventId]: detail }))
    } catch (error) {
      if (!controller.signal.aborted) setDetailErrors((current) => ({ ...current, [eventId]: errorMessage(error) }))
    } finally {
      if (!controller.signal.aborted) setDetailLoading(undefined)
    }
  }

  return (
    <section className="page narrow">
      <header className="page-header">
        <div>
          <p className="eyebrow">STORY LINE · 04</p>
          <h1>关系会随故事改变</h1>
          <p>时间线把静态关系放回章节语境，区分“曾经属于”和“此刻属于”。</p>
        </div>
        <label className="select-label">人物
          <select aria-label="人物" value={person} onChange={(event) => setPerson(event.target.value)}>
            <option value="">全部人物</option>
            {people.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
      </header>
      <ol className="timeline">
        {events.map((item) => {
          const isExpanded = expandedId === item.event.id
          const panelId = `timeline-detail-${item.event.id}`
          return (
            <li key={item.event.id}>
              <span>{item.chapter_number ? `第 ${item.chapter_number} 章` : '章节待考'}</span>
              <article className="timeline-event">
                <button className="timeline-event-trigger" type="button" aria-expanded={isExpanded} aria-controls={panelId} onClick={() => void toggleEvent(item.event.id)}>
                  <span>
                    <span className="eyebrow">{item.event.type}</span>
                    <strong>{item.event.name}</strong>
                    {item.event.description && <small>{item.event.description}</small>}
                  </span>
                  <span className="timeline-event-chevron" aria-hidden="true">{isExpanded ? '−' : '+'}</span>
                </button>
                {isExpanded && (
                  <div id={panelId}>
                    {detailLoading === item.event.id && <p className="timeline-detail-status" role="status">正在加载事件详情…</p>}
                    {detailErrors[item.event.id] && (
                      <div className="timeline-detail-error" role="alert">
                        <span><strong>详情加载失败</strong><small>{detailErrors[item.event.id]}</small></span>
                        <button type="button" onClick={() => void toggleEvent(item.event.id, true)}>重试</button>
                      </div>
                    )}
                    {details[item.event.id] && detailLoading !== item.event.id && (
                      <EventDetail
                        detail={details[item.event.id]}
                        onViewGraph={() => navigate({ pathname: '/graph', search: `?project=${encodeURIComponent(projectId)}&entity=${encodeURIComponent(item.event.id)}` })}
                      />
                    )}
                  </div>
                )}
              </article>
            </li>
          )
        })}
        {events.length === 0 && <li className="empty-state">当前条件下没有事件</li>}
      </ol>
    </section>
  )
}
