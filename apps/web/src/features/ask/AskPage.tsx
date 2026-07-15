import { FormEvent, useEffect, useState } from 'react'

import {
  apiFetch,
  getQaSuggestions,
  type AskResponse,
  type QaSuggestion,
} from '../../api/client'
import { useProject } from '../../app/ProjectContext'
import { StatusDot } from '../../components/StatusDot'

export function AskPage() {
  const { projectId, projects } = useProject()
  const projectTitle = projects.find(project => project.id === projectId)?.title ?? '当前项目'

  return <AskProjectPage key={projectId} projectId={projectId} projectTitle={projectTitle} />
}

function AskProjectPage({ projectId, projectTitle }: { projectId: string; projectTitle: string }) {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<AskResponse>()
  const [loading, setLoading] = useState(false)
  const [details, setDetails] = useState(false)
  const [suggestions, setSuggestions] = useState<QaSuggestion[]>([])
  const [suggestionsLoading, setSuggestionsLoading] = useState(true)
  const [suggestionsError, setSuggestionsError] = useState(false)
  const [serverProjectTitle, setServerProjectTitle] = useState('')
  const displayProjectTitle = projectTitle === '当前项目'
    ? serverProjectTitle || projectTitle
    : projectTitle

  useEffect(() => {
    const controller = new AbortController()
    setSuggestionsLoading(true)
    setSuggestionsError(false)

    getQaSuggestions(projectId, controller.signal)
      .then(response => {
        if (response.project_id !== projectId) return
        setServerProjectTitle(response.project_title)
        setSuggestions(response.suggestions)
      })
      .catch(error => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setSuggestionsError(true)
        setSuggestions([])
      })
      .finally(() => {
        if (!controller.signal.aborted) setSuggestionsLoading(false)
      })

    return () => controller.abort()
  }, [projectId])

  const ask = async (event?: FormEvent) => {
    event?.preventDefault()
    const trimmedQuestion = question.trim()
    if (!trimmedQuestion) return
    setLoading(true)
    setDetails(false)
    try {
      setAnswer(await apiFetch<AskResponse>('/api/ask', {
        method: 'POST',
        body: JSON.stringify({ project_id: projectId, question: trimmedQuestion }),
      }))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="page ask-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">EXPLAINABLE QA · 05</p>
          <h1>答案不是猜出来的</h1>
          <p>每个回答同时展示图路径与原文证据；查不到时，系统明确拒答。</p>
        </div>
      </header>
      <div className="ask-layout">
        <div>
          <form onSubmit={ask} className="ask-form">
            <label htmlFor="question">向《{displayProjectTitle}》图谱提问</label>
            <div>
              <input
                id="question"
                value={question}
                onChange={event => setQuestion(event.target.value)}
              />
              <button className="primary" disabled={loading || !question.trim()}>
                {loading ? '查询中…' : '查询图谱'}
              </button>
            </div>
          </form>
          <div className="sample-questions" aria-live="polite">
            {suggestionsLoading && <p>正在生成当前项目的问题建议…</p>}
            {!suggestionsLoading && suggestionsError && <p>问题建议暂时不可用，仍可手动提问</p>}
            {!suggestionsLoading && !suggestionsError && suggestions.length === 0 && (
              <p>当前项目暂无可推荐的问题</p>
            )}
            {!suggestionsLoading && !suggestionsError && suggestions.map(suggestion => (
              <button
                type="button"
                key={suggestion.id}
                onClick={() => setQuestion(suggestion.question)}
              >
                {suggestion.question}
              </button>
            ))}
          </div>
        </div>
        {answer ? (
          <article className="answer-card" aria-live="polite">
            <StatusDot tone={answer.evidence.length > 0 ? 'success' : 'warning'}>
              {answer.evidence.length > 0 ? '已找到可验证答案' : '答案缺少原文证据'}
            </StatusDot>
            <h2>{answer.answer}</h2>
            {answer.path.map((step, index) => (
              <div className="answer-path" key={index}>
                <span>{step.source_name}</span>
                <b>— {step.relation} →</b>
                <span>{step.target_name}</span>
              </div>
            ))}
            {answer.evidence.map(item => (
              <blockquote key={item.id}>
                <small>第 {item.chapter_number} 章 · {item.chapter_title}</small>
                <p>{item.quote}</p>
              </blockquote>
            ))}
            <button className="text-button" onClick={() => setDetails(!details)}>
              查看技术细节 {details ? '↑' : '↓'}
            </button>
            {details && (
              <div className="tech-details">
                <p>{answer.query_explanation}</p>
                <pre>{answer.cypher_template || '未执行查询模板'}</pre>
                <code>{JSON.stringify(answer.parameters)}</code>
              </div>
            )}
          </article>
        ) : (
          <div className="answer-empty">
            <p>选择一个示例问题，观察答案如何由图事实和原文证据共同产生。</p>
          </div>
        )}
      </div>
    </section>
  )
}
