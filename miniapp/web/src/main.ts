import { createApp } from 'vue';
import App from './App.vue';
import './styles/tokens.css';
import './styles/themes.css';
if (window.WebApp?.initData) {
  document.documentElement.classList.add('in-max');
}
createApp(App).mount('#app');
