import cytoscape from 'cytoscape'
import { useEffect, useRef } from 'react'

import type { Neighborhood } from '../../api/client'
import { getEntityTypeStyle } from './entityTypeStyles'

export function GraphCanvas({ graph, onSelect }: { graph: Neighborhood; onSelect: (id: string) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current || graph.nodes.length === 0) return
    const cy = cytoscape({
      container: ref.current.clientWidth ? ref.current : undefined,
      headless: ref.current.clientWidth === 0,
      elements: [
        ...graph.nodes.map(node => ({ data: { id: node.id, label: node.name, type: node.type, color: getEntityTypeStyle(node.type).color } })),
        ...graph.edges.map(edge => ({ data: { id: edge.id, source: edge.source_id, target: edge.target_id, label: edge.type } })),
      ],
      style: [
        { selector: 'node', style: { 'background-color': 'data(color)', color: '#24211d', label: 'data(label)', 'font-family': 'system-ui', 'font-size': 12, 'text-valign': 'bottom', 'text-margin-y': 8, width: 32, height: 32 } },
        { selector: 'node[type = "Person"]', style: { width: 38, height: 38 } },
        { selector: 'edge', style: { width: 1.5, 'line-color': '#b9b1a4', 'target-arrow-color': '#b9b1a4', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', label: 'data(label)', 'font-size': 8, color: '#736b60' } },
      ],
      layout: { name: 'cose', animate: false, padding: 32 },
    })
    cy.on('tap', 'node', event => onSelect(event.target.id()))
    return () => cy.destroy()
  }, [graph, onSelect])
  return <div ref={ref} className="graph-canvas" aria-label="知识图谱画布">{graph.nodes.length === 0 && <div className="canvas-empty"><b>从一个人物开始</b><p>搜索实体后，图谱只展开相关邻居，避免全图失控。</p></div>}</div>
}
