import { useProject } from '../../app/ProjectContext'
import { DEFAULT_PROJECT_ID } from '../../api/client'

export function ProjectSwitcher() {
  const {
    projects,
    projectId,
    setProjectId,
    projectSwitchLocked,
  } = useProject()
  const userProjects = projects.filter(item => !item.is_builtin)
  const visibleProjects = userProjects.length > 0 ? userProjects : projects
  return <label className="project-switcher"><span>当前项目</span><select aria-label="当前项目" value={projectId} disabled={projectSwitchLocked} title={projectSwitchLocked ? '构建完成前不能切换项目' : undefined} onChange={event => setProjectId(event.target.value)}>{visibleProjects.length === 0 && <option value={DEFAULT_PROJECT_ID}>笑傲江湖</option>}{visibleProjects.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
}
