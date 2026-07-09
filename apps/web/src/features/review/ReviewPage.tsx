import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  apiFetch,
  type ReviewAction,
  type ReviewActionRequest,
  type ReviewItem,
  type ReviewSummary as Summary,
} from '../../api/client'
import { useProject } from '../../app/ProjectContext'
import { AuditDrawer } from './AuditDrawer'
import { EntityMergePanel } from './EntityMergePanel'
import { ReviewDetail } from './ReviewDetail'
import { ReviewQueue } from './ReviewQueue'
import { ReviewSummary } from './ReviewSummary'

const EMPTY_SUMMARY: Summary = {
  open_review_items: 0,
  accepted_facts: 0,
  rejected_facts: 0,
  pending_facts: 0,
  merged_entities: 0,
  split_aliases: 0,
  evidence_coverage: 0,
  review_completion_rate: 0,
  graph_fact_delta_before_after_review: 0,
}

export function ReviewPage() {
  const { projectId } = useProject()
  const [summary, setSummary] = useState<Summary>(EMPTY_SUMMARY)
  const [items, setItems] = useState<ReviewItem[]>([])
  const [actions, setActions] = useState<ReviewAction[]>([])
  const [selectedId, setSelectedId] = useState<string>()
  const selected = useMemo(
    () => items.find((item) => item.id === selectedId) ?? items[0],
    [items, selectedId],
  )

  const refreshReview = useCallback(() => {
    apiFetch<Summary>(`/api/projects/${projectId}/review/summary`).then(setSummary)
    apiFetch<{ items: ReviewItem[] }>(`/api/projects/${projectId}/review/items?status=OPEN&limit=50`).then(
      (body) => setItems(body.items),
    )
    apiFetch<{ actions: ReviewAction[] }>(`/api/projects/${projectId}/review/audit?limit=20`).then((body) =>
      setActions(body.actions),
    )
  }, [projectId])

  useEffect(() => {
    refreshReview()
  }, [refreshReview])

  function applyAction(request: ReviewActionRequest) {
    if (!selected) return
    apiFetch(`/api/projects/${projectId}/review/items/${selected.id}/actions`, {
      method: 'POST',
      body: JSON.stringify(request),
    }).then(() => {
      setItems((current) => current.filter((item) => item.id !== selected.id))
      refreshReview()
    })
  }

  return (
    <section className="review-page">
      <header>
        <p className="eyebrow">REVIEW · PHASE 3</p>
        <h1>审核工作台</h1>
      </header>
      <ReviewSummary summary={summary} />
      <EntityMergePanel projectId={projectId} onMerged={refreshReview} />
      <div className="review-workspace">
        <ReviewQueue items={items} selectedId={selected?.id} onSelect={(item) => setSelectedId(item.id)} />
        <ReviewDetail item={selected} onAction={applyAction} />
        <AuditDrawer actions={actions} />
      </div>
    </section>
  )
}
