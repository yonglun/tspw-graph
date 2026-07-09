import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { ProjectProvider, useProject } from './ProjectContext'
import { ProjectSwitcher } from '../features/projects/ProjectSwitcher'

function Probe() { const { projectId } = useProject(); return <span>{projectId}</span> }

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
  expect(screen.getByLabelText('当前项目')).toHaveValue('project-full')
  expect(screen.getByRole('option', { name: '笑傲江湖完整版' })).toBeInTheDocument()
  expect(screen.queryByRole('option', { name: '笑傲江湖' })).not.toBeInTheDocument()
})
