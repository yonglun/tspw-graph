import type { ReactNode } from 'react'

import type { AttributeDetail, EntityDetail, Evidence } from '../../api/client'

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
  const attributes = detail.attributes ?? []
  const relations = detail.relations ?? []
  const groupedAttributes = groupAttributes(attributes)
  return <aside className="entity-panel" aria-label="实体详情"><button className="icon-button" aria-label="关闭实体详情" onClick={onClose}>×</button><p className="eyebrow">{detail.type}</p><h2>{detail.name}</h2><p>{detail.description}</p>{detail.aliases.length > 0 && <p className="aliases">别名 · {detail.aliases.join('、')}</p>}<hr /><h3>本体属性</h3>{attributes.length === 0 ? <p className="empty-note">尚未抽取到有证据支持的属性</p> : <dl className="attribute-list">{groupedAttributes.map(group => <div key={group.label}><dt>{group.label}</dt><dd>{group.values.join('、')}</dd></div>)}</dl>}<h3>关系摘要</h3>{relations.length === 0 ? <p className="empty-note">暂无关系摘要</p> : <ul className="relation-list">{relations.map(relation => <li key={relation.fact_id}><span>{relation.label}</span><b>{relation.other.name}</b></li>)}</ul>}<h3>属性证据</h3>{attributes.length === 0 ? <p className="empty-note">暂无属性证据</p> : attributes.flatMap(attribute => attribute.evidence.map(evidence => <EvidenceQuote key={`${attribute.id}-${evidence.id}`} evidence={evidence} footer={`${attribute.label} · ${attribute.value} · 字符 ${evidence.start_offset}–${evidence.end_offset}`} />))}<h3>关系证据</h3>{detail.facts.flatMap(fact => fact.evidence.map(evidence => <EvidenceQuote key={`${fact.id}-${evidence.id}`} evidence={evidence} footer={`${fact.type} · 字符 ${evidence.start_offset}–${evidence.end_offset}`}><button type="button" onClick={() => onReviewFact?.(fact.id)}>加入审核</button></EvidenceQuote>))}</aside>
}

function EvidenceQuote({ evidence, footer, children }: { evidence: Evidence; footer: string; children?: ReactNode }) {
  return <blockquote><small>第{toChinese(evidence.chapter_number)}章 · {evidence.chapter_title}</small><p>{evidence.quote}</p><footer>{footer}</footer>{children}</blockquote>
}

function groupAttributes(attributes: AttributeDetail[]) {
  const groups = new Map<string, string[]>()
  for (const attribute of attributes) {
    const values = groups.get(attribute.label) ?? []
    if (!values.includes(attribute.value)) values.push(attribute.value)
    groups.set(attribute.label, values)
  }
  return Array.from(groups, ([label, values]) => ({ label, values }))
}

function toChinese(value: number) {
  const values: Record<number, string> = { 5: '五', 10: '十', 22: '二十二', 35: '三十五' }
  return values[value] ?? String(value)
}
