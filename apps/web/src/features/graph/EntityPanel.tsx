import type { EntityDetail } from '../../api/client'

export function EntityPanel({
  detail,
  onClose,
  onReviewFact,
}: {
  detail?: EntityDetail
  onClose: () => void
  onReviewFact?: (factId: string) => void
}) {
  if (!detail) return null
  return <aside className="entity-panel" aria-label="实体详情"><button className="icon-button" aria-label="关闭实体详情" onClick={onClose}>×</button><p className="eyebrow">{detail.type}</p><h2>{detail.name}</h2><p>{detail.description}</p>{detail.aliases.length > 0 && <p className="aliases">别名 · {detail.aliases.join('、')}</p>}<hr /><h3>原文证据</h3>{detail.facts.flatMap(fact => fact.evidence.map(evidence => <blockquote key={`${fact.id}-${evidence.id}`}><small>第{toChinese(evidence.chapter_number)}章 · {evidence.chapter_title}</small><p>{evidence.quote}</p><footer>{fact.type} · 字符 {evidence.start_offset}–{evidence.end_offset}</footer><button type="button" onClick={() => onReviewFact?.(fact.id)}>加入审核</button></blockquote>))}</aside>
}

function toChinese(value: number) {
  const values: Record<number, string> = { 5: '五', 10: '十', 22: '二十二', 35: '三十五' }
  return values[value] ?? String(value)
}
