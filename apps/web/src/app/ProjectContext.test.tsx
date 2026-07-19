import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { ProjectProvider, useProject } from './ProjectContext'
import { ProjectSwitcher } from '../features/projects/ProjectSwitcher'

function Probe() { const { projectId } = useProject(); return <span>{projectId}</span> }
function LocationProbe() { return <span data-testid="location">{useLocation().search}</span> }

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('restores the selected project from the URL', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([]))))
  render(<MemoryRouter initialEntries={['/graph?project=project-1']}><ProjectProvider><Probe /></ProjectProvider></MemoryRouter>)
  expect(await screen.findByText('project-1')).toBeVisible()
})

it('prefers the first user project over the builtin demo project', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([
    { id: 'xiaoao', title: '笑傲江湖', is_builtin: true, source_encoding: null, source_size: null, created_at: '', updated_at: '' },
    { id: 'project-full', title: '笑傲江湖完整版', is_builtin: false, source_encoding: 'utf-8', source_size: 1, created_at: '', updated_at: '' },
  ]))))
  render(<MemoryRouter initialEntries={['/graph?project=xiaoao']}><ProjectProvider><Probe /><ProjectSwitcher /></ProjectProvider></MemoryRouter>)

  expect(await screen.findByText('project-full')).toBeVisible()
  const switcher = screen.getByRole('button', { name: '当前项目' })
  expect(switcher).toHaveTextContent('笑傲江湖完整版')
  await userEvent.setup().click(switcher)
  expect(screen.getByRole('option', { name: '笑傲江湖完整版' })).toBeInTheDocument()
  expect(screen.queryByRole('option', { name: '笑傲江湖' })).not.toBeInTheDocument()
})

it('removes an entity deep link when switching projects', async () => {
  const user = userEvent.setup()
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([
    { id: 'project-1', title: '项目一', is_builtin: false, source_encoding: 'utf-8', source_size: 1, created_at: '', updated_at: '' },
    { id: 'project-2', title: '项目二', is_builtin: false, source_encoding: 'utf-8', source_size: 1, created_at: '', updated_at: '' },
  ]))))
  render(
    <MemoryRouter initialEntries={['/graph?project=project-1&entity=entity-from-project-1']}>
      <ProjectProvider><ProjectSwitcher /><LocationProbe /></ProjectProvider>
    </MemoryRouter>,
  )

  await user.click(await screen.findByRole('button', { name: '当前项目' }))
  await user.click(screen.getByRole('option', { name: '项目二' }))

  expect(screen.getByTestId('location')).toHaveTextContent('?project=project-2')
  expect(screen.getByTestId('location')).not.toHaveTextContent('entity=')
})
