import { useEffect, useState } from 'react'

import { apiFetch, type OntologyCatalog } from '../../api/client'

export function OntologyPage() {
  const [catalog, setCatalog] = useState<OntologyCatalog>()
  const [error, setError] = useState('')
  const [view, setView] = useState<'tbox' | 'abox'>('tbox')
  const [expandedTypeId, setExpandedTypeId] = useState<string>()

  useEffect(() => {
    apiFetch<OntologyCatalog>('/api/ontology').then(setCatalog).catch((e: Error) => setError(e.message))
  }, [])

  return <section className="page">
    <header className="page-header">
      <div>
        <p className="eyebrow">ONTOLOGY · 02</p>
        <h1>先定义江湖，再描述江湖</h1>
        <p>本体不是一张漂亮的关系图，而是一套对所有事实生效的概念与约束。</p>
      </div>
      <div className="segmented" aria-label="本体视图">
        <button className={view === 'tbox' ? 'active' : ''} onClick={() => setView('tbox')}>TBox 概念层</button>
        <button className={view === 'abox' ? 'active' : ''} onClick={() => setView('abox')}>ABox 实例层</button>
      </div>
    </header>
    {error && <div role="alert" className="error-state">{error}</div>}
    {!catalog && !error && <div className="skeleton" aria-label="正在加载本体" />}
    {catalog && view === 'tbox' && <div className="ontology-grid">
      {catalog.entity_types.map(type => {
        const expanded = expandedTypeId === type.id
        const properties = type.effective_property_definitions ?? type.property_definitions ?? []
        const propertyPanelId = `type-properties-${type.id}`
        return <article className={`type-card${expanded ? ' is-expanded' : ''}`} key={type.id} aria-label={`${type.label} ${type.id}`}>
          <button
            type="button"
            className="type-card-toggle"
            aria-expanded={expanded}
            aria-controls={propertyPanelId}
            onClick={() => setExpandedTypeId(expanded ? undefined : type.id)}
          >
            <span className="type-card-kind"><i className="entity-type-dot" data-testid="entity-type-dot" style={{ backgroundColor: type.color }} aria-hidden="true" />{type.parent ? '子类' : '核心类'}</span>
            <h2>{type.label}</h2>
            <code>{type.id}</code>
            <p>{type.description}</p>
            {type.parent && <small>继承自 {type.parent}</small>}
            <b>{expanded ? '收起属性' : `查看属性（${properties.length}）`}</b>
          </button>
          {expanded && <div className="type-properties" id={propertyPanelId}>
            <h3>有效属性</h3>
            {properties.length === 0 ? <p className="empty-note">该类暂无属性定义</p> : <dl>
              {properties.map(property => <div key={property.id}>
                <dt>{property.label} <code>{property.id}</code></dt>
                <dd>{property.description}<small>{property.value_type}{property.multiple ? ' · 可多值' : ''}{property.enum_values.length > 0 ? ` · ${property.enum_values.join('、')}` : ''}</small></dd>
              </div>)}
            </dl>}
          </div>}
        </article>
      })}
    </div>}
    {catalog && view === 'abox' && <figure className="abox" aria-label="ABox 实例关系示例">
      <div className="abox-flow">
        <div className="abox-node" role="group" aria-label="主体实例">
          <span>人物实例</span>
          <h2>{catalog.example.subject}</h2>
          <code>Person</code>
        </div>
        <div className="abox-edge" role="group" aria-label="关系类型">
          <span>关系类型</span>
          <strong>掌握</strong>
          <code>{catalog.example.predicate}</code>
          <i className="abox-arrow" aria-hidden="true" />
        </div>
        <div className="abox-node" role="group" aria-label="客体实例">
          <span>武学实例</span>
          <h2>{catalog.example.object}</h2>
          <code>Swordplay</code>
        </div>
      </div>
      <aside className="abox-rule-card">
        <div>
          <p className="abox-rule-status"><i aria-hidden="true" />通过约束检查</p>
          <h3>这条事实为什么有效？</h3>
          <p>{catalog.example.predicate} 的主体必须是人物，客体必须是武学。</p>
        </div>
        <details>
          <summary>查看原始三元组</summary>
          <pre><code>{JSON.stringify(catalog.example, null, 2)}</code></pre>
        </details>
      </aside>
      <figcaption>ABox 用本体定义的类型与关系，描述具体人物、武学和事实。</figcaption>
    </figure>}
  </section>
}
