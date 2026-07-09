import { useEffect, useState } from 'react'

import { apiFetch, type EntitySummary } from '../../api/client'

type Slot = 'source' | 'target'

type SelectionState = {
  query: string
  results: EntitySummary[]
  selected?: EntitySummary
}

const emptySelection: SelectionState = { query: '', results: [] }

export function EntityMergePanel({
  projectId,
  onMerged,
}: {
  projectId: string
  onMerged: () => void
}) {
  const [source, setSource] = useState<SelectionState>(emptySelection)
  const [target, setTarget] = useState<SelectionState>(emptySelection)
  const [message, setMessage] = useState('')

  useEntitySearch(projectId, source.query, (results) =>
    setSource((current) => ({ ...current, results })),
  )
  useEntitySearch(projectId, target.query, (results) =>
    setTarget((current) => ({ ...current, results })),
  )

  function updateQuery(slot: Slot, query: string) {
    const setter = slot === 'source' ? setSource : setTarget
    setter({ query, results: [], selected: undefined })
    setMessage('')
  }

  function select(slot: Slot, entity: EntitySummary) {
    const setter = slot === 'source' ? setSource : setTarget
    setter({ query: entity.name, results: [], selected: entity })
    setMessage('')
  }

  async function merge() {
    if (!source.selected || !target.selected) {
      setMessage('请先选择源实体和目标实体')
      return
    }
    if (source.selected.id === target.selected.id) {
      setMessage('源实体和目标实体不能相同')
      return
    }
    await apiFetch(`/api/projects/${projectId}/review/entities/merge`, {
      method: 'POST',
      body: JSON.stringify({
        source_entity_id: source.selected.id,
        target_entity_id: target.selected.id,
      }),
    })
    setSource(emptySelection)
    setTarget(emptySelection)
    setMessage('实体已合并')
    onMerged()
  }

  return (
    <section className="entity-merge-panel">
      <p className="eyebrow">ENTITY MERGE</p>
      <h2>手工合并实体</h2>
      <p>把模型误识别出的重复实体并入标准实体，关系、事实和别名会一起迁移。</p>
      <div className="entity-merge-grid">
        <EntityPicker
          id="merge-source"
          label="源实体"
          value={source.query}
          results={source.results}
          selected={source.selected}
          onChange={(value) => updateQuery('source', value)}
          onSelect={(entity) => select('source', entity)}
          buttonPrefix="选择源实体"
        />
        <EntityPicker
          id="merge-target"
          label="目标实体"
          value={target.query}
          results={target.results}
          selected={target.selected}
          onChange={(value) => updateQuery('target', value)}
          onSelect={(entity) => select('target', entity)}
          buttonPrefix="选择目标实体"
        />
      </div>
      <button type="button" onClick={merge} disabled={!source.selected || !target.selected}>
        合并实体
      </button>
      {message && <p className="merge-message">{message}</p>}
    </section>
  )
}

function EntityPicker({
  id,
  label,
  value,
  results,
  selected,
  onChange,
  onSelect,
  buttonPrefix,
}: {
  id: string
  label: string
  value: string
  results: EntitySummary[]
  selected?: EntitySummary
  onChange: (value: string) => void
  onSelect: (entity: EntitySummary) => void
  buttonPrefix: string
}) {
  return (
    <div className="entity-picker">
      <label htmlFor={id}>{label}</label>
      <input id={id} value={value} onChange={(event) => onChange(event.target.value)} />
      {selected && (
        <small>
          已选：{selected.name} · {selected.type}
        </small>
      )}
      {results.length > 0 && (
        <div className="entity-picker-results">
          {results.map((entity) => (
            <button
              key={entity.id}
              type="button"
              aria-label={`${buttonPrefix} ${entity.name}`}
              onClick={() => onSelect(entity)}
            >
              <b>{entity.name}</b>
              <span>{entity.type}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function useEntitySearch(projectId: string, query: string, onResults: (results: EntitySummary[]) => void) {
  useEffect(() => {
    if (!query.trim()) {
      onResults([])
      return
    }
    let active = true
    apiFetch<EntitySummary[]>(
      `/api/graph/search?project_id=${projectId}&query=${encodeURIComponent(query)}`,
    )
      .then((results) => {
        if (active) onResults(results)
      })
      .catch(() => {
        if (active) onResults([])
      })
    return () => {
      active = false
    }
  }, [projectId, query])
}
