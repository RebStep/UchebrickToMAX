import { local } from './format';
import type { Olympiad, Task } from './types';
const SAMARA_OFFSET_H = 4;
const at = (daysFromNow: number, hh: number, mm = 0) => {
  const l = local(new Date());
  return new Date(Date.UTC(l.y, l.m - 1, l.d + daysFromNow, hh - SAMARA_OFFSET_H, mm)).toISOString();
};
const base = { location: null, note: null, reg_deadline: null, status: 'active' as const, x: null, y: null, files: [] };
export function mockTasks(): Task[] {
  return [
    {
      ...base, id: 1, title: 'Решить №12–18 на стр. 54, сделать чертёж к задаче 15', subject: 'Математика', kind: 'homework', due_at: at(1, 23, 59), x: 40, y: 140,
      files: [
        { id: 11, task_id: 1, type: 'photo', name: 'Доска.jpg', x: 620, y: 140 },
        { id: 12, task_id: 1, type: 'doc', name: 'Формулы.pdf', hint: 'отправить в чат', x: 620, y: 310 },
        { id: 13, task_id: 1, type: 'link', name: 'youtu.be/Xk3656…', url: 'https://youtu.be/Xk3656', x: 620, y: 390 },
      ]
    },
    { ...base, id: 2, title: 'Лабораторная работа по оптике', subject: 'Физика', kind: 'homework', due_at: at(0, 23, 59), location: 'каб. 305', x: 40, y: 360 },
    { ...base, id: 3, title: 'Сочинение по «Евгению Онегину»', subject: 'Русский язык', kind: 'homework', due_at: at(-1, 23, 59), x: 330, y: 360 },
    { ...base, id: 4, title: 'Параграф 21, ответить на вопросы', subject: 'Английский язык', kind: 'homework', due_at: at(3, 23, 59), status: 'done', x: 40, y: 540 },
    { ...base, id: 5, title: 'Всероссийская олимпиада, школьный этап', subject: 'Олимпиада', kind: 'olympiad', due_at: at(8, 15, 0), location: 'каб. 214', reg_deadline: at(4, 23, 59), x: 330, y: 540 },
    { ...base, id: 6, title: 'Взять калькулятор', subject: null, kind: 'todo', due_at: at(1, 8, 0), x: 40, y: 700, files: [{ id: 14, task_id: 6, type: 'note', name: 'Взять калькулятор', text: 'Взять калькулятор\nи запасные батарейки', x: 620, y: 700 }] },
  ];
}
const day = (n: number) => at(n, 0);
export function mockOlympiads(): Olympiad[] {
  return [
    {
      id: 1, name: 'Технокубок', level: null, subject: 'Информатика', location: 'каб. 214', note: 'Решать можно в любой день, взять паспорт', registered: false,
      reg_opens: day(-3), reg_deadline: day(4),
      tours: [{ id: 1, title: 'Отборочный', starts_at: day(24), deadline: day(41), done: false }, { id: 2, title: 'Заключительный', starts_at: day(78), deadline: day(91), done: false }]
    },
    {
      id: 2, name: 'ВсОШ, школьный этап, по иностранному языку', level: null, subject: 'Английский язык', location: null, note: null, registered: true,
      reg_opens: day(11), reg_deadline: day(30), tours: [{ id: 3, title: 'Школьный', starts_at: day(38), deadline: day(48), done: false }]
    },
    {
      id: 3, name: 'Курчатов', level: null, subject: 'Физика', location: null, note: null, registered: true, reg_opens: null, reg_deadline: null,
      tours: [{ id: 4, title: 'Тур', starts_at: day(41), deadline: day(41), done: false }]
    },
    {
      id: 4, name: 'Ломоносов', level: null, subject: 'Математика', location: null, note: null, registered: true, reg_opens: null, reg_deadline: null,
      tours: [{ id: 5, title: 'Тур', starts_at: day(77), deadline: day(91), done: false }]
    },
    {
      id: 5, name: 'Физтех', level: null, subject: 'Физика', location: null, note: null, registered: true, reg_opens: null, reg_deadline: null,
      tours: [{ id: 6, title: 'Тур', starts_at: day(-3), deadline: day(5), done: true }]
    },
    { id: 6, name: 'Олимпиада без дат', level: null, subject: null, location: null, note: null, registered: false, reg_opens: null, reg_deadline: null, tours: [] },
  ];
}
