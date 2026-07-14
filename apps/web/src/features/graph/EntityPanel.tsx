import { type ReactNode, useEffect } from 'react'

import type { AttributeDetail, EntityDetail, Evidence, RelationEvidence } from '../../api/client'

export function EntityPanel({
  detail,
  onClose,
  onReviewFact,
  onSelectRelation,
  onSelectAttribute,
  selectedRelationId,
  selectedAttributeId,
  relationEvidence,
}: {
  detail?: EntityDetail
  onClose: () => void
  onReviewFact?: (factId: string) => void
  onSelectRelation?: (factId: string) => void
  onSelectAttribute?: (attributeId: string) => void
  selectedRelationId?: string
  selectedAttributeId?: string
  relationEvidence?: RelationEvidence
}) {
  useEffect(() => {
    const target = selectedAttributeId
      ? document.getElementById(`attribute-evidence-${selectedAttributeId}`)
      : selectedRelationId
        ? document.getElementById(`relation-evidence-${selectedRelationId}`)
        : undefined
    if (target && 'scrollIntoView' in target) target.scrollIntoView({ block: 'nearest' })
  }, [selectedAttributeId, selectedRelationId, relationEvidence])

  if (!detail) return null
  const attributes = detail.attributes ?? []
  const relations = detail.relations ?? []
  const groupedAttributes = groupAttributes(attributes)
  const facts = relationEvidence ? [relationEvidence] : detail.facts

  return <aside className="entity-panel" aria-label="实体详情">
    <button className="icon-button" aria-label="关闭实体详情" onClick={onClose}>×</button>
    <p className="eyebrow">{detail.type}</p><h2>{detail.name}</h2><p>{detail.description}</p>
    {detail.aliases.length > 0 && <p className="aliases">别名 · {detail.aliases.join('、')}</p>}
    <hr /><h3>本体属性</h3>
    {attributes.length === 0 ? <p className="empty-note">尚未抽取到有证据支持的属性</p> : <dl className="attribute-list">{groupedAttributes.map(group => {
      const selected = group.ids.includes(selectedAttributeId ?? '')
      return <div key={group.label} className={selected ? 'is-selected' : ''}>
        <dt><button type="button" aria-label={`${group.label} ${group.values.join('、')}`} aria-pressed={selected} onClick={() => onSelectAttribute?.(group.ids[0])}>{group.label}</button></dt>
        <dd>{group.values.join('、')}</dd>
      </div>
    })}</dl>}
    <h3>关系摘要</h3>
    {relations.length === 0 ? <p className="empty-note">暂无关系摘要</p> : <ul className="relation-list">{relations.map(relation => {
      const selected = relation.fact_id === selectedRelationId
      return <li key={relation.fact_id} className={selected ? 'is-selected' : ''}>
        <button type="button" aria-pressed={selected} onClick={() => onSelectRelation?.(relation.fact_id)}><span>{relation.label}</span><b>{relation.other.name}</b></button>
      </li>
    })}</ul>}
    <h3>属性证据</h3>
    {attributes.length === 0 ? <p className="empty-note">暂无属性证据</p> : attributes.flatMap(attribute => attribute.evidence.map(evidence => <EvidenceQuote key={`${attribute.id}-${evidence.id}`} id={`attribute-evidence-${attribute.id}`} evidence={evidence} selected={attribute.id === selectedAttributeId} footer={`${attribute.label} · ${attribute.value} · 字符 ${evidence.start_offset}–${evidence.end_offset}`} />))}
    <h3>关系证据</h3>
    {facts.flatMap(fact => fact.evidence.map(evidence => <EvidenceQuote key={`${fact.id}-${evidence.id}`} id={`relation-evidence-${fact.id}`} evidence={evidence} selected={fact.id === selectedRelationId} footer={`${fact.type} · 字符 ${evidence.start_offset}–${evidence.end_offset}`}><button type="button" onClick={() => onReviewFact?.(fact.id)}>加入审核</button></EvidenceQuote>))}
  </aside>
}

function EvidenceQuote({ id, evidence, footer, children, selected }: { id?: string; evidence: Evidence; footer: string; children?: ReactNode; selected?: boolean }) {
  return <blockquote id={id} className={selected ? 'is-selected' : undefined}><small>第{toChinese(evidence.chapter_number)}章 · {evidence.chapter_title}</small><p>{evidence.quote}</p><footer>{footer}</footer>{children}</blockquote>
}

function groupAttributes(attributes: AttributeDetail[]) {
  const groups = new Map<string, { values: string[]; ids: string[] }>()
  for (const attribute of attributes) {
    const group = groups.get(attribute.label) ?? { values: [], ids: [] }
    if (!group.values.includes(attribute.value)) group.values.push(attribute.value)
    group.ids.push(attribute.id)
    groups.set(attribute.label, group)
  }
  return Array.from(groups, ([label, group]) => ({ label, ...group }))
}

function toChinese(value: number) {
  const values: Record<number, string> = { 5: '五', 10: '十', 22: '二十二', 35: '三十五' }
  return values[value] ?? String(value)
}
