import { useState } from 'react'
import { Link } from 'react-router-dom'

const steps = [
  { label: '事实', title: '三个元素，组成一条知识', body: '“令狐冲掌握独孤九剑”可以拆成主体、关系、客体。图谱保存的不是一段文字，而是可计算的事实。' },
  { label: '本体', title: '本体定义世界的规则', body: '本体规定“人物”可以掌握“武学”，也规定关系方向、时间范围和证据要求。它是所有数据共同遵守的语义契约。' },
  { label: '连接', title: '事实连接后形成图谱', body: '同一个人物连接门派、师承、武学与事件。沿着关系寻路，就能回答普通关键词检索难以解释的问题。' },
  { label: '证据', title: '每个答案都回到原文', body: '节点和关系不是模型的自由发挥。确认事实必须绑定章节、字符偏移和短引文，答案因此可以审计。' },
]

export function GuidePage() {
  const [step, setStep] = useState(0)
  const current = steps[step]
  return <section className="guide-page">
    <div className="guide-copy">
      <p className="eyebrow">KNOWLEDGE GRAPH LAB · 01</p>
      <h1>看懂《笑傲江湖》<br />也看懂知识图谱</h1>
      <p className="lede">用十分钟，从一句小说事实走到可查询、可解释、可追溯的知识网络。</p>
      <div className="step-tabs" aria-label="导览进度">{steps.map((item, index) => <button key={item.label} className={index === step ? 'active' : ''} onClick={() => setStep(index)}><span>0{index + 1}</span>{item.label}</button>)}</div>
      <article className="lesson" aria-live="polite"><p className="eyebrow">{current.label}</p><h2>{current.title}</h2><p>{current.body}</p></article>
      {step < steps.length - 1 ? <button className="primary" onClick={() => setStep(step + 1)}>{step === 0 ? '下一步：什么是本体' : '继续导览'} <span aria-hidden="true">→</span></button> : <Link className="button primary" to="/graph">开始探索图谱 →</Link>}
    </div>
    <div className="triple-card" role="group" aria-label="知识三元组示例">
      <div className="triple-node subject"><small>人物</small><strong>令狐冲</strong></div>
      <div className="relation"><span>掌握</span><i aria-hidden="true" /></div>
      <div className="triple-node object"><small>剑法</small><strong>独孤九剑</strong></div>
      <p>主体 — 关系 — 客体，构成一条可查询事实。</p>
    </div>
  </section>
}
