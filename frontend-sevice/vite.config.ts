import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'

const backendTarget = process.env.VITE_API_PROXY_TARGET || process.env.AIP_BACKEND_URL || 'http://localhost:8080'

// Vite 插件：记录服务器启动时间
function serverStartTimePlugin() {
  return {
    name: 'server-start-time',
    async configureServer() {
      // 服务器启动时记录时间
      const startTime = {
        start_time: new Date().toISOString(),
        timestamp: Date.now()
      };
      
      const filePath = path.resolve(__dirname, 'public/server-info.json');
      fs.writeFileSync(filePath, JSON.stringify(startTime, null, 2));
      
      console.log('✓ 前端服务器启动时间已记录到文件:', startTime.start_time);
      
      // 延迟并重试记录到后端数据库
      const recordToDatabase = async (retries = 8, initialDelay = 3000) => {
        for (let i = 0; i < retries; i++) {
          try {
            // 等待一段时间，让后端完全启动
            // 第一次等待更长时间，后续逐渐减少
            const delay = i === 0 ? initialDelay : 2000;
            
            if (i === 0) {
              console.log(`⏳ 等待 ${delay/1000} 秒让后端完全初始化（数据库、路由等）...`);
            } else {
              console.log(`⏳ 重试连接后端... (尝试 ${i + 1}/${retries})`);
            }
            
            await new Promise(resolve => setTimeout(resolve, delay));
            
            const response = await fetch(`${backendTarget}/api/system/service-status`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                service_name: 'frontend',
                service_type: 'web',
                status: 'running',
                version: '0.1.0',
                host: 'localhost',
                port: 3001
              })
            });
            
            if (response.ok) {
              const data = await response.json();
              console.log('✓ 前端服务状态已成功记录到数据库:', data.start_time);
              console.log('  数据库记录ID:', data.service_id);
              return; // 成功，退出重试循环
            } else {
              const errorText = await response.text();
              console.log(`⚠ 后端返回错误 (${response.status}):`, errorText);
              if (i === retries - 1) {
                console.log('❌ 无法记录前端服务状态到数据库（已尝试 ' + retries + ' 次）');
                console.log('   前端服务状态仅保存在本地文件: public/server-info.json');
                console.log('   建议：检查后端服务是否正常启动，数据库表是否正确创建');
              }
            }
          } catch (error: any) {
            if (i === retries - 1) {
              console.log('❌ 无法连接到后端数据库（已尝试 ' + retries + ' 次）');
              console.log('   错误信息:', error.message || error);
              console.log('   前端服务状态仅保存在本地文件: public/server-info.json');
              console.log('   建议：');
              console.log('   1. 确保后端服务已启动: http://localhost:8080');
              console.log('   2. 检查后端控制台是否有错误信息');
              console.log('   3. 访问 http://localhost:8080/docs 查看API文档');
            }
          }
        }
      };
      
      // 异步执行，不阻塞服务器启动
      recordToDatabase();
    }
  };
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    serverStartTimePlugin()
  ],
  server: {
    host: '0.0.0.0',
    port: 3001,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true,
        secure: false,
      },
      '/llm': {
        target: backendTarget,
        changeOrigin: true,
        secure: false,
      }
    }
  }
})
