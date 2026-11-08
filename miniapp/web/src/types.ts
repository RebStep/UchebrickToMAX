export type Kind = 'homework' | 'todo' | 'event' | 'project' | 'olympiad'
export type FileType = 'photo' | 'doc' | 'link' | 'note'

export interface FileItem {
  id: number
  task_id: number | null
  type: FileType
  name: string
  hint?: string
  url?: string | null
  text?: string
  x: number | null
  y: number | null
}

export interface Task {
  id: number
  title: string
  subject: string | null
  kind: Kind
  due_at: string | null
  location: string | null
  note: string | null
  reg_deadline: string | null
  duration_min?: number | null
  registered?: boolean
  planned_at?: string | null
  status: 'active' | 'done'
  x: number | null
  y: number | null
  created_at?: string | null
  files: FileItem[]
}

export interface Tour {
  id: number
  title: string
  starts_at: string | null
  deadline: string | null
  duration_min?: number | null
  done: boolean
}

export interface Olympiad {
  id: number
  name: string
  level: string | null
  subject: string | null
  location: string | null
  note: string | null
  registered: boolean
  reg_opens: string | null
  reg_deadline: string | null
  tours: Tour[]
  links?: string[]
  reminders_muted?: boolean
}
