import { useProject } from '../../app/ProjectContext'
import { DEFAULT_PROJECT_ID } from '../../api/client'

export function ProjectSwitcher() {
  const { projects, projectId, setProjectId } = useProject()
  const userProjects = projects.filter(item => !item.is_builtin)
  const visibleProjects = userProjects.length > 0 ? userProjects : projects
  return <label className="project-switcher"><span>当前项目</span><select aria-label="当前项目" value={projectId} onChange={event => setProjectId(event.target.value)}>{visibleProjects.length === 0 && <option value={DEFAULT_PROJECT_ID}>笑傲江湖</option>}{visibleProjects.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
}
