import type { Task } from './types';
const KIND_GROUP: Record<string, string> = { homework: 'Домашка', todo: 'Дела', event: 'События', project: 'Проекты', olympiad: 'Олимпиада' };
export const KIND_GROUPS = new Set(Object.values(KIND_GROUP));
export const groupOf = (t: Pick<Task, 'subject' | 'kind'>) => {
  if (t.kind === 'olympiad') {
    return 'Олимпиада';
  }
  return t.subject ?? KIND_GROUP[t.kind] ?? 'Дела';
};
