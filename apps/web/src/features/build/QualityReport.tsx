import { Link } from 'react-router-dom'
import { type QualityReport as Report } from '../../api/client'
import { useProject } from '../../app/ProjectContext'

export function QualityReport({ report, projectId }: { report: Report; projectId: string }) {
  const { setProjectId } = useProject(); const metrics = [['实体', report.accepted_entities], ['事实', report.accepted_facts], ['证据', report.accepted_evidence], ...(report.accepted_attributes === undefined ? [] : [['属性', report.accepted_attributes]]), ...(report.accepted_attribute_evidence === undefined ? [] : [['属性证据', report.accepted_attribute_evidence]]), ['拒绝项', Object.values(report.rejected_by_code).reduce((a, b) => a + b, 0)]]
  return <section className="quality-report"><p className="eyebrow">03 · QUALITY</p><h2>质量报告</h2><div className="quality-metrics">{metrics.map(([label, value]) => <div key={label} data-testid={label === '事实' ? 'accepted-facts' : undefined}><strong>{value}</strong><span>{label}</span></div>)}</div>{Object.keys(report.rejected_by_code).length > 0 && <ul>{Object.entries(report.rejected_by_code).map(([code, count]) => <li key={code}>{code} · {count}</li>)}</ul>}<Link className="button primary" to={`/graph?project=${projectId}`} onClick={() => setProjectId(projectId)}>进入项目图谱</Link></section>
}
