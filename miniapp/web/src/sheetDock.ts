import { computed, reactive, ref } from 'vue';
const FOLDED_WIDTH = 58;
const GAP = 12;
export function createSheetDock() {
  const desktop = ref(false);
  const panels = reactive<{
    id: symbol;
    key?: string;
    width: number;
    collapsed: boolean;
  }[]>([]);
  const folded = computed(() => panels.filter((p) => p.collapsed));
  const foldedCount = computed(() => folded.value.length);
  function collapseAll() {
    if (desktop.value) {
      panels.forEach((p) => { p.collapsed = true; });
    }
  }
  function activate(id: symbol | string) {
    const panel = panels.find((p) => {
      if (typeof id === 'string') {
        return p.key === id;
      }
      return p.id === id;
    });
    if (!panel) {
      return;
    }
    collapseAll();
    panel.collapsed = false;
  }
  function register(width: number, key?: string) {
    const id = Symbol(key);
    panels.push({ id, key, width, collapsed: false });
    activate(id);
    return panels.find((p) => p.id === id)!;
  }
  function unregister(id: symbol) {
    const index = panels.findIndex((p) => p.id === id);
    if (index >= 0) {
      panels.splice(index, 1);
    }
  }
  function right(id: symbol) {
    const isFolded = folded.value.some((p) => p.id === id);
    return GAP + (!isFolded && foldedCount.value ? FOLDED_WIDTH + GAP : 0);
  }
  const foldedIndex = (id: symbol) => Math.max(0, folded.value.findIndex((p) => p.id === id));
  const inset = computed(() => {
    if (desktop.value) {
      return (foldedCount.value ? FOLDED_WIDTH + GAP : 0)
        + panels.reduce((sum, p) => sum + (p.collapsed ? 0 : p.width + GAP), 0);
    }
    return 0;
  });
  return { desktop, panels, inset, register, unregister, activate, collapseAll, right, foldedCount, foldedIndex };
}
export const sheetDock = createSheetDock();
