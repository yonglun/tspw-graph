import cytoscape from 'cytoscape'
import { useEffect, useRef } from 'react'

import type { Neighborhood } from '../../api/client'
import { getEntityTypeStyle } from './entityTypeStyles'

export function GraphCanvas({
  graph,
  centerId,
  onSelect,
  selectedRelationId,
  onSelectEdge,
}: {
  graph: Neighborhood
  centerId?: string
  onSelect: (id: string) => void
  selectedRelationId?: string
  onSelectEdge: (id: string) => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current || graph.nodes.length === 0) return
    const cy = cytoscape({
      container: ref.current.clientWidth ? ref.current : undefined,
      headless: ref.current.clientWidth === 0,
      elements: [
        ...graph.nodes.map(node => ({ data: { id: node.id, label: node.name, type: node.type, color: getEntityTypeStyle(node.type).color, center: node.id === centerId } })),
        ...graph.edges.map(edge => ({ data: { id: edge.id, source: edge.source_id, target: edge.target_id, label: edge.type, selected: edge.id === selectedRelationId } })),
      ],
      style: [
        { selector: 'node', style: { 'background-color': 'data(color)', color: '#4d4d4d', label: 'data(label)', 'font-family': 'Geist Sans, system-ui', 'font-size': 10, 'font-weight': 400, 'text-valign': 'bottom', 'text-margin-y': 6, width: 10, height: 10 } },
        { selector: 'node[center = "true"]', style: { width: 14, height: 14, 'border-width': 3, 'border-color': '#0072f5', 'border-opacity': 1, color: '#171717', 'font-size': 11, 'font-weight': 500 } },
        { selector: 'edge', style: { width: 1, 'line-color': '#d4d4d4', 'target-arrow-color': '#d4d4d4', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', label: 'data(label)', 'font-size': 8, color: '#8f8f8f', 'text-background-color': '#fafafa', 'text-background-opacity': .8, 'text-background-padding': '2px' } },
        { selector: 'edge[selected = "true"]', style: { width: 2, 'line-color': '#0072f5', 'target-arrow-color': '#0072f5', color: '#0072f5', 'font-size': 9 } },
      ],
      layout: {
        name: 'concentric',
        animate: false,
        padding: 32,
        minNodeSpacing: 48,
        concentric: node => (node.id() === centerId ? 2 : 1),
        levelWidth: () => 1,
      },
    })
    cy.on('tap', 'node', event => onSelect(event.target.id()))
    cy.on('tap', 'edge', event => onSelectEdge(event.target.id()))
    return () => cy.destroy()
  }, [centerId, graph, onSelect, onSelectEdge, selectedRelationId])
  return <div ref={ref} className="graph-canvas" aria-label="知识图谱画布">{graph.nodes.length === 0 && <div className="canvas-empty"><b>从一个人物开始</b><p>搜索实体后，图谱只展开相关邻居，避免全图失控。</p></div>}<ul className="graph-node-list" aria-label="图谱节点">{graph.nodes.map(node => <li key={node.id}>{node.name}</li>)}</ul></div>
}
