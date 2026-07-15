import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router/index.js'
import './assets/global.css'

// Element Plus 按需加载：服务式组件（通过 JS 函数调用）的样式需手动引入
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/notification/style/css'
import 'element-plus/es/components/loading/style/css'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.mount('#app')
