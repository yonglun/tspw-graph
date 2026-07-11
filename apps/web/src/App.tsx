import { BrowserRouter, NavLink } from 'react-router-dom'

import { AppRoutes } from './app/router'
import { ProjectProvider, useProject } from './app/ProjectContext'
import { ProjectSwitcher } from './features/projects/ProjectSwitcher'
import './styles/theme.css'
import './styles/swiss.css'

const links = [['/guide', '导览'], ['/ontology', '本体'], ['/graph', '图谱'], ['/story', '故事线'], ['/ask', '问答'], ['/build', '构建'], ['/review', '审核']]

function projectPath(path: string, projectId: string) {
  return { pathname: path, search: `?project=${encodeURIComponent(projectId)}` }
}

function SiteHeader() {
  const { projectId } = useProject()
  return <header className="site-header"><NavLink className="brand" to={projectPath('/guide', projectId)}><span>江湖</span>图谱</NavLink><nav aria-label="主导航">{links.map(([path, label]) => <NavLink key={path} to={projectPath(path, projectId)}>{label}</NavLink>)}</nav><ProjectSwitcher /></header>
}

export function App() {
  return <BrowserRouter><ProjectProvider><a className="skip-link" href="#main">跳到主要内容</a><SiteHeader /><main id="main"><AppRoutes /></main></ProjectProvider></BrowserRouter>
}
