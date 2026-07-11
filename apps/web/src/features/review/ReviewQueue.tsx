import type { ReviewItem } from '../../api/client'

export function ReviewQueue({
  items,
  selectedId,
  onSelect,
}: {
  items: ReviewItem[]
  selectedId?: string
  onSelect: (item: ReviewItem) => void
}) {
  return (
    <aside className="review-queue">
      <h2>审核队列</h2>
      {items.map((item) => (
        <button
          className={item.id === selectedId ? 'active' : ''}
          key={item.id}
          onClick={() => onSelect(item)}
        >
          <b>{reasonLabel(item.reason_code)}</b>
          <span>{item.item_type === 'FACT' ? '待确认事实' : item.item_type} · {item.source}</span>
          <small>严重度 {item.severity} · {item.target.fact_id ?? item.target.entity_id ?? item.id}</small>
          <em>{item.reason_code}</em>
        </button>
      ))}
    </aside>
  )
}

function reasonLabel(code: string) {
  const labels: Record<string, string> = {
    LOW_CONFIDENCE_FACT: '低置信度事实',
    EVIDENCE_MISMATCH: '证据不匹配',
    UNKNOWN_RELATION_TYPE: '未知关系类型',
    MANUAL_REVIEW_FACT: '人工复核事实',
    DUPLICATE_ENTITY: '疑似重复实体',
    ALIAS_SPLIT: '别名拆分',
  }
  return labels[code] ?? code
}
