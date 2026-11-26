import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
const proxy = Object.fromEntries(Object.entries({station:8001,billing:8002,dispatch:8003,saga:8004,gateway:8005}).map(([name,port])=>[`/${name}`,{target:`http://localhost:${port}`,changeOrigin:true,rewrite:(path:string)=>path.replace(new RegExp(`^/${name}`),'')}]))
export default defineConfig({plugins:[react(),tailwindcss()],server:{port:5173,proxy:{...proxy,'/graphql':{target:'http://localhost:8005',changeOrigin:true}}}})
