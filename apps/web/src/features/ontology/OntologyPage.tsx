import { useEffect, useState } from 'react'

import { apiFetch, type OntologyCatalog } from '../../api/client'

export function OntologyPage() {
  const [catalog, setCatalog] = useState<OntologyCatalog>()
  const [error, setError] = useState('')
  const [view, setView] = useState<'tbox' | 'abox'>('tbox')
  const [expandedTypeId, setExpandedTypeId] = useState<string>()
  useEffect(() => { apiFetch<OntologyCatalog>('/api/ontology').then(setCatalog).catch((e: Error) => setError(e.message)) }, [])
  return <section className="page">
    <header className="page-header"><div><p className="eyebrow">ONTOLOGY · 02</p><h1>先定义江湖，再描述江湖</h1><p>本体不是一张漂亮的关系图，而是一套对所有事实生效的概念与约束。</p></div><div className="segmented"><button className={view === 'tbox' ? 'active' : ''} onClick={() => setView('tbox')}>TBox 概念层</button><button className={view === 'abox' ? 'active' : ''} onClick={() => setView('abox')}>ABox 实例层</button></div></header>
    {error && <div role="alert" className="error-state">{error}</div>}
    {!catalog && !error && <div className="skeleton" aria-label="正在加载本体" />}
    {catalog && view === 'tbox' && <div className="ontology-grid">{catalog.entity_types.map(type => { const expanded = expandedTypeId === type.id; const properties = type.effective_property_definitions ?? type.property_definitions ?? []; return <article className={`type-card${expanded ? ' is-expanded' : ''}`} key={type.id} style={{ '--type-color': type.color } as React.CSSProperties}><button type="button" className="type-card-toggle" aria-expanded={expanded} onClick={() => setExpandedTypeId(expanded ? undefined : type.id)}><span>{type.parent ? '子类' : '核心类'}</span><h2>{type.label}</h2><code>{type.id}</code><p>{type.description}</p>{type.parent && <small>继承自 {type.parent}</small>}<b>{expanded ? '收起属性' : `查看属性（${properties.length}）`}</b></button>{expanded && <div className="type-properties"><h3>有效属性</h3>{properties.length === 0 ? <p className="empty-note">该类暂无属性定义</p> : <dl>{properties.map(property => <div key={property.id}><dt>{property.label} <code>{property.id}</code></dt><dd>{property.description}<small>{property.value_type}{property.multiple ? ' · 可多值' : ''}{property.enum_values.length > 0 ? ` · ${property.enum_values.join('、')}` : ''}</small></dd></div>)}</dl>}</div>}</article>})}</div>}
    {catalog && view === 'abox' && <div className="abox"><div className="abox-node">令狐冲 <small>Person</small></div><div className="abox-edge">— 掌握 →</div><div className="abox-node accent">独孤九剑 <small>Swordplay</small></div><aside><b>满足本体约束</b><p>KNOWS 的主体必须是人物，客体必须是武学。</p><code>{JSON.stringify(catalog.example, null, 2)}</code></aside></div>}
  </section>
}
