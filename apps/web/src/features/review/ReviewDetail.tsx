import type { ReviewActionRequest, ReviewItem, RelationEvidence } from '../../api/client'

export function ReviewDetail({
  item,
  fact,
  factLoading,
  factError,
  onAction,
}: {
  item?: ReviewItem
  fact?: RelationEvidence
  factLoading?: boolean
  factError?: string
  onAction: (request: ReviewActionRequest) => void
}) {
  if (!item) {
    return <section className="review-detail"><h2>选择一个待审核项</h2><p className="review-empty">从左侧队列选择一条记录，查看事实、证据和审核原因。</p></section>
  }

  const factId = item.target.fact_id ?? ''
  const sourceName = fact?.source?.name ?? fact?.source_id ?? '未知主体'
  const targetName = fact?.target?.name ?? fact?.target_id ?? '未知客体'
  const relationLabel = fact?.label ?? fact?.type ?? '关系'
  const evidence = fact?.evidence ?? []

  return <section className="review-detail">
    <div className="review-detail-heading"><div><p className="eyebrow">{item.item_type === 'FACT' ? 'FACT TO REVIEW' : item.item_type}</p><h2>需要审核的内容</h2></div><span className="severity-badge">严重度 {item.severity}</span></div>
    <div className="review-reason"><b>{reasonLabel(item.reason_code)}</b><span>{item.source === 'manual' ? '人工提交' : item.source === 'model' ? '模型发现' : '规则发现'}</span><p>{reasonDescription(item.reason_code)}</p></div>
    {item.item_type === 'FACT' ? <>
      {factLoading && <p className="review-loading" role="status">正在加载事实和原文证据…</p>}
      {factError && <p className="review-error" role="alert">事实详情加载失败：{factError}</p>}
      <div className="fact-triple" aria-label="待审核事实"><span>{sourceName}</span><b>{relationLabel}</b><span>{targetName}</span></div>
      {evidence.length ? <div className="review-evidence"><h3>原文证据</h3>{evidence.map(item => <blockquote key={item.id}><small>第{item.chapter_number}章 · {item.chapter_title} · 字符 {item.start_offset}–{item.end_offset}</small><p>{item.quote}</p></blockquote>)}</div> : <p className="review-empty">暂无可展示的原文证据，请谨慎处理。</p>}
      <details className="review-technical"><summary>查看技术标识</summary><code>{factId}</code>{item.evidence_ids.length > 0 && <small>证据 ID：{item.evidence_ids.join('、')}</small>}</details>
    </> : <div className="review-target"><h3>待处理对象</h3><pre>{JSON.stringify(item.target, null, 2)}</pre></div>}
    <div className="review-actions">
      {item.item_type === 'FACT' && <><button onClick={() => onAction({ action_type: 'accept_fact', payload: { fact_id: factId }, idempotency_key: `accept-${item.id}` })}>接受事实</button><button onClick={() => onAction({ action_type: 'reject_fact', payload: { fact_id: factId }, idempotency_key: `reject-${item.id}` })}>拒绝事实</button></>}
      <button onClick={() => onAction({ action_type: 'dismiss_item', payload: {}, idempotency_key: `dismiss-${item.id}` })}>忽略</button>
    </div>
  </section>
}

function reasonLabel(code: string) {
  const labels: Record<string, string> = { LOW_CONFIDENCE_FACT: '低置信度事实', EVIDENCE_MISMATCH: '证据不匹配', UNKNOWN_RELATION_TYPE: '未知关系类型', MANUAL_REVIEW_FACT: '人工复核事实', DUPLICATE_ENTITY: '疑似重复实体', ALIAS_SPLIT: '别名拆分' }
  return labels[code] ?? code
}

function reasonDescription(code: string) {
  const descriptions: Record<string, string> = { LOW_CONFIDENCE_FACT: '模型对这条关系的判断置信度较低，需要结合原文确认。', EVIDENCE_MISMATCH: '抽取的关系与原文证据可能不一致。', UNKNOWN_RELATION_TYPE: '关系类型不在当前本体定义中。', MANUAL_REVIEW_FACT: '这条事实由用户或系统主动提交复核。' }
  return descriptions[code] ?? '请结合事实三元组和原文证据做出判断。'
}
