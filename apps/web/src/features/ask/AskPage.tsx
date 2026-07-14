import { FormEvent, useState } from 'react'

import { apiFetch, type AskResponse } from '../../api/client'
import { useProject } from '../../app/ProjectContext'
import { StatusDot } from '../../components/StatusDot'

const samples = ['令狐冲的师父是谁？', '令狐冲掌握什么武功？', '令狐冲属于哪个门派？', '令狐冲的性别是什么？', '令狐冲有哪些称号？', '令狐冲的生日是哪天？']

export function AskPage() {
  const { projectId } = useProject()
  const [question, setQuestion] = useState(samples[0])
  const [answer, setAnswer] = useState<AskResponse>()
  const [loading, setLoading] = useState(false)
  const [details, setDetails] = useState(false)
  const ask = async (event?: FormEvent) => { event?.preventDefault(); setLoading(true); setDetails(false); try { setAnswer(await apiFetch<AskResponse>('/api/ask', { method: 'POST', body: JSON.stringify({ project_id: projectId, question }) })) } finally { setLoading(false) } }
  return <section className="page ask-page"><header className="page-header"><div><p className="eyebrow">EXPLAINABLE QA · 05</p><h1>答案不是猜出来的</h1><p>每个回答同时展示图路径与原文证据；查不到时，系统明确拒答。</p></div></header><div className="ask-layout"><div><form onSubmit={ask} className="ask-form"><label htmlFor="question">向《笑傲江湖》图谱提问</label><div><input id="question" value={question} onChange={event => setQuestion(event.target.value)} /><button className="primary" disabled={loading}>{loading ? '查询中…' : '查询图谱'}</button></div></form><div className="sample-questions">{samples.map(sample => <button key={sample} onClick={() => setQuestion(sample)}>{sample}</button>)}</div></div>{answer ? <article className="answer-card" aria-live="polite"><StatusDot tone={answer.evidence.length > 0 ? 'success' : 'warning'}>{answer.evidence.length > 0 ? '已找到可验证答案' : '答案缺少原文证据'}</StatusDot><h2>{answer.answer}</h2>{answer.path.map((step, index) => <div className="answer-path" key={index}><span>{step.source_name}</span><b>— {step.relation} →</b><span>{step.target_name}</span></div>)}{answer.evidence.map(item => <blockquote key={item.id}><small>第 {item.chapter_number} 章 · {item.chapter_title}</small><p>{item.quote}</p></blockquote>)}<button className="text-button" onClick={() => setDetails(!details)}>查看技术细节 {details ? '↑' : '↓'}</button>{details && <div className="tech-details"><p>{answer.query_explanation}</p><pre>{answer.cypher_template || '未执行查询模板'}</pre><code>{JSON.stringify(answer.parameters)}</code></div>}</article> : <div className="answer-empty"><p>选择一个示例问题，观察答案如何由图事实和原文证据共同产生。</p></div>}</div></section>
}
