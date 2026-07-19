import { useLocation } from 'react-router-dom'

import { useProject } from '../../app/ProjectContext'
import { DEFAULT_PROJECT_ID } from '../../api/client'
import { ViewportListbox } from './ViewportListbox'

export function ProjectSwitcher() {
  const location = useLocation()
  const {
    projects,
    projectId,
    setProjectId,
    projectSwitchLocked,
  } = useProject()
  const userProjects = projects.filter(item => !item.is_builtin)
  const visibleProjects = userProjects.length > 0 ? userProjects : projects
  const options = visibleProjects.length > 0
    ? visibleProjects.map(item => ({ value: item.id, label: item.title }))
    : [{ value: DEFAULT_PROJECT_ID, label: '笑傲江湖' }]

  return (
    <div className="project-switcher">
      <span>当前项目</span>
      <ViewportListbox
        label="当前项目"
        value={projectId}
        options={options}
        disabled={projectSwitchLocked}
        disabledTitle="构建完成前不能切换项目"
        dismissSignal={`${location.pathname}${location.search}`}
        onChange={setProjectId}
      />
    </div>
  )
}
