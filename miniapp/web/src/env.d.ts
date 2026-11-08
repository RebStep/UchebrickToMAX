declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

interface MaxWebApp {
  initData: string
  ready?: () => void
}
interface Window {
  WebApp?: MaxWebApp
}
