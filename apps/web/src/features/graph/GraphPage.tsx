import { type CSSProperties, useCallback, useEffect, useRef, useState } from 'react'

import { apiFetch, type EntityDetail, type EntitySummary, type Neighborhood, type RelationEvidence } from '../../api/client'
import { useProject } from '../../app/ProjectContext'
import { EntityPanel } from './EntityPanel'
import { GraphCanvas } from './GraphCanvas'
import { visibleEntityTypeStyles } from './entityTypeStyles'

const EMPTY_GRAPH: Neighborhood = { nodes: [], edges: [] }

export function GraphPage() {
  const { projectId } = useProject()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<EntitySummary[]>([])
  const [graph, setGraph] = useState<Neighborhood>(EMPTY_GRAPH)
  const [detail, setDetail] = useState<EntityDetail>()
  const [selected, setSelected] = useState<EntitySummary>()
  const [graphDepth, setGraphDepth] = useState<1 | 2>(1)
  const [graphLoading, setGraphLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedRelationId, setSelectedRelationId] = useState<string>()
  const [selectedAttributeId, setSelectedAttributeId] = useState<string>()
  const [relationEvidence, setRelationEvidence] = useState<RelationEvidence>()
  const [relationEvidenceLoading, setRelationEvidenceLoading] = useState(false)
  const graphRequest = useRef<AbortController | undefined>(undefined)
  const detailRequest = useRef<AbortController | undefined>(undefined)

  const abortEntityRequests = useCallback(() => {
    graphRequest.current?.abort()
    detailRequest.current?.abort()
    graphRequest.current = undefined
    detailRequest.current = undefined
  }, [])

  useEffect(() => {
    if (!query.trim()) { setResults([]); setError(''); return }
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      apiFetch<EntitySummary[]>(`/api/graph/search?project_id=${projectId}&query=${encodeURIComponent(query)}`, { signal: controller.signal })
        .then(nextResults => { setResults(nextResults); setError('') })
        .catch((e: Error) => { if (e.name !== 'AbortError') setError(e.message) })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [query, projectId])

  useEffect(() => {
    abortEntityRequests()
    setResults([])
    setGraph(EMPTY_GRAPH)
    setDetail(undefined)
    setSelected(undefined)
    setGraphDepth(1)
    setGraphLoading(false)
    setError('')
    setSelectedRelationId(undefined)
    setSelectedAttributeId(undefined)
    setRelationEvidence(undefined)
    setRelationEvidenceLoading(false)
    return () => abortEntityRequests()
  }, [abortEntityRequests, projectId])

  const selectEntity = useCallback((entity: EntitySummary) => {
    abortEntityRequests()
    setSelected(entity)
    setResults([])
    setError('')
    setDetail(undefined)
    setSelectedRelationId(undefined)
    setSelectedAttributeId(undefined)
    setRelationEvidence(undefined)
    setGraphDepth(1)
    setGraph({ nodes: [entity], edges: [] })
    setGraphLoading(true)
    const nextGraphRequest = new AbortController()
    const nextDetailRequest = new AbortController()
    graphRequest.current = nextGraphRequest
    detailRequest.current = nextDetailRequest

    apiFetch<Neighborhood>(`/api/graph/neighborhood?project_id=${projectId}&entity_id=${encodeURIComponent(entity.id)}&depth=1&limit=50`, { signal: nextGraphRequest.signal })
      .then(nextGraph => { setGraph(nextGraph); setGraphDepth(1) })
      .catch((e: Error) => { if (e.name !== 'AbortError') setError(e.message) })
      .finally(() => { if (!nextGraphRequest.signal.aborted) setGraphLoading(false) })

    apiFetch<EntityDetail>(`/api/entities/${encodeURIComponent(entity.id)}?project_id=${projectId}`, { signal: nextDetailRequest.signal })
      .then(nextDetail => setDetail(nextDetail))
      .catch((e: Error) => { if (e.name !== 'AbortError') setError(e.message) })
  }, [abortEntityRequests, projectId])

  const selectEntityById = useCallback((id: string) => {
    const entity = graph.nodes.find(node => node.id === id)
    if (entity) selectEntity(entity)
  }, [graph.nodes, selectEntity])

  const expandTwoHop = useCallback(() => {
    if (!selected) return
    graphRequest.current?.abort()
    const controller = new AbortController()
    graphRequest.current = controller
    setGraphLoading(true)
    setError('')
    apiFetch<Neighborhood>(`/api/graph/neighborhood?project_id=${projectId}&entity_id=${encodeURIComponent(selected.id)}&depth=2&limit=100`, { signal: controller.signal })
      .then(nextGraph => { setGraph(nextGraph); setGraphDepth(2) })
      .catch((e: Error) => { if (e.name !== 'AbortError') setError(e.message) })
      .finally(() => { if (!controller.signal.aborted) setGraphLoading(false) })
  }, [projectId, selected])

  function reviewFact(factId: string) {
    apiFetch(`/api/projects/${projectId}/review/items`, {
      method: 'POST',
      body: JSON.stringify({
        item_type: 'FACT',
        reason_code: 'MANUAL_REVIEW',
        target: { fact_id: factId },
        evidence_ids: [],
        fingerprint: `manual:${factId}`,
        severity: 10,
      }),
    }).catch((e: Error) => setError(e.message))
  }
  const selectRelation = useCallback((factId: string) => {
    setSelectedRelationId(factId)
    setSelectedAttributeId(undefined)
    setRelationEvidence(undefined)
    setRelationEvidenceLoading(true)
    apiFetch<RelationEvidence>(`/api/graph/relations/${encodeURIComponent(factId)}?project_id=${projectId}`)
      .then(setRelationEvidence)
      .catch((e: Error) => setError(e.message))
      .finally(() => setRelationEvidenceLoading(false))
  }, [projectId])

  const selectAttribute = useCallback((attributeId: string) => {
    setSelectedAttributeId(attributeId)
    setSelectedRelationId(undefined)
    setRelationEvidence(undefined)
  }, [])

  return <section className="graph-page"><header className="graph-toolbar"><div><p className="eyebrow">GRAPH EXPLORER · 03</p><h1>沿关系，游江湖</h1></div><div className="search-wrap"><label htmlFor="graph-search">搜索人物、门派或武学</label><input id="graph-search" type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="例如：令狐冲" />{results.length > 0 && <div className="search-results">{results.map(item => <button key={item.id} onClick={() => selectEntity(item)}><b>{item.name}</b><span>{item.type} · {item.description}</span></button>)}</div>}</div></header>{error && <div role="alert" className="error-state">{error}</div>}{relationEvidenceLoading && <div className="loading-state" role="status">正在加载关系证据…</div>}<div className="graph-workspace"><GraphCanvas graph={graph} centerId={selected?.id} selectedRelationId={selectedRelationId} onSelect={selectEntityById} onSelectEdge={selectRelation} /><EntityPanel detail={detail} onClose={() => { setDetail(undefined); setSelectedRelationId(undefined); setSelectedAttributeId(undefined); setRelationEvidence(undefined) }} onReviewFact={reviewFact} onSelectRelation={selectRelation} onSelectAttribute={selectAttribute} selectedRelationId={selectedRelationId} selectedAttributeId={selectedAttributeId} relationEvidence={relationEvidence} /></div><footer className="graph-legend">{visibleEntityTypeStyles(graph.nodes).map(type => <span key={type.label}><i style={{ '--legend-color': type.color } as CSSProperties} />{type.label}</span>)}{selected && graphDepth === 1 && !graphLoading && <button type="button" className="text-button" onClick={expandTwoHop}>展开二度关系</button>}<b>{graph.nodes.length} 节点 · {graph.edges.length} 关系</b></footer></section>
}
