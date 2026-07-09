import type { EntitySummary } from '../../api/client'

type EntityTypeStyle = { label: string; color: string; order: number }

const ENTITY_TYPE_STYLES: Record<string, EntityTypeStyle> = {
  Person: { label: '人物', color: '#4f46e5', order: 0 },
  Organization: { label: '组织', color: '#059669', order: 1 },
  Sect: { label: '门派', color: '#10b981', order: 2 },
  Clan: { label: '家族', color: '#34d399', order: 3 },
  EscortAgency: { label: '镖局', color: '#6ee7b7', order: 4 },
  PoliticalForce: { label: '政治势力', color: '#047857', order: 5 },
  MartialArt: { label: '武学', color: '#d97706', order: 6 },
  Swordplay: { label: '剑法', color: '#f59e0b', order: 7 },
  InternalSkill: { label: '内功', color: '#fbbf24', order: 8 },
  PalmTechnique: { label: '掌法', color: '#fcd34d', order: 9 },
  Qinggong: { label: '轻功', color: '#fde68a', order: 10 },
  MusicScore: { label: '曲谱', color: '#fef3c7', order: 11 },
  Event: { label: '事件', color: '#dc2626', order: 12 },
  TeachingEvent: { label: '传授事件', color: '#ef4444', order: 13 },
  Place: { label: '地点', color: '#0891b2', order: 14 },
  Artifact: { label: '物品', color: '#7c3aed', order: 15 },
}

const FALLBACK_STYLE: EntityTypeStyle = { label: '其他实体', color: '#24211d', order: 999 }

export function getEntityTypeStyle(type: string): EntityTypeStyle {
  return ENTITY_TYPE_STYLES[type] ?? { ...FALLBACK_STYLE, label: type || FALLBACK_STYLE.label }
}

export function visibleEntityTypeStyles(nodes: EntitySummary[]): EntityTypeStyle[] {
  const byType = new Map<string, EntityTypeStyle>()
  for (const node of nodes) {
    if (!byType.has(node.type)) byType.set(node.type, getEntityTypeStyle(node.type))
  }
  return [...byType.values()].sort((left, right) => left.order - right.order || left.label.localeCompare(right.label))
}
