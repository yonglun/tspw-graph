import { BrowserRouter, NavLink } from 'react-router-dom'

import { AppRoutes } from './app/router'
import { ProjectProvider, useProject } from './app/ProjectContext'
import { AuthProvider, useAuth } from './app/AuthContext'
import { LoginIcon, LogoutIcon } from './components/AuthIcons'
import { ProjectSwitcher } from './features/projects/ProjectSwitcher'
import './styles/base.css'
import './styles/vercel.css'

const publicLinks = [['/guide', '导览'], ['/ontology', '本体'], ['/graph', '图谱'], ['/story', '故事线'], ['/ask', '问答']]
const adminLinks = [['/build', '构建'], ['/review', '审核'], ['/admin', '管理员']]

function projectPath(path: string, projectId: string) {
  return { pathname: path, search: `?project=${encodeURIComponent(projectId)}` }
}

function SiteHeader() {
  const { projectId } = useProject()
  const auth = useAuth()
  const links = auth.status === 'ready' ? [...publicLinks, ...adminLinks] : publicLinks
  return <header className="site-header"><NavLink aria-label="江湖图谱" className="brand" to={projectPath('/guide', projectId)}><span className="brand-mark" aria-hidden="true">江</span><span className="brand-name">江湖图谱</span></NavLink><nav aria-label="主导航">{links.map(([path, label]) => <NavLink key={path} to={projectPath(path, projectId)}>{label}</NavLink>)}</nav><div className="header-tools"><ProjectSwitcher />{auth.status === 'ready' ? <button className="auth-icon-control" type="button" aria-label="退出管理员登录" title="退出管理员登录" onClick={() => void auth.logout()}><LogoutIcon /></button> : auth.status === 'anonymous' ? <NavLink className="auth-icon-control" aria-label="管理员登录" title="管理员登录" to="/login"><LoginIcon /></NavLink> : null}</div></header>
}

export function App() {
  return <BrowserRouter><AuthProvider><ProjectProvider><a className="skip-link" href="#main">跳到主要内容</a><SiteHeader /><main id="main"><AppRoutes /></main></ProjectProvider></AuthProvider></BrowserRouter>
}
