<template>
  <div class="footer_box">
    <div class="footer-content">
      <div class="left-section">
        <span class="version">BrickCore v{{ platformVersion }}</span>
        <span class="divider">|</span>
        <span class="tech">Powered by FastAPI + Vue3</span>
      </div>
      <div class="center-section">
        © 2025-2026 All Rights Reserved.
      </div>
      <div class="right-section">
        <el-tooltip content="系统运行正常" placement="top">
          <div class="status">
            <span class="status-dot"></span>
            <span class="status-text">系统正常</span>
          </div>
        </el-tooltip>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import http from '@/api/request'

const platformVersion = ref('1.2')

onMounted(async () => {
  try {
    const res = await http.get('/runner/version')
    if (res.data?.platform_version) {
      platformVersion.value = res.data.platform_version
    }
  } catch {
    // 保持默认展示
  }
})
</script>

<style scoped lang="scss">
.footer_box {
  height: 40px;
  background: var(--el-fill-color-light);
  border-top: 1px solid var(--el-border-color-lighter);
  
  .footer-content {
    height: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 20px;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    
    .left-section {
      display: flex;
      align-items: center;
      gap: 10px;
      
      .version {
        font-weight: 600;
        color: var(--el-color-primary);
      }
      
      .divider {
        color: var(--el-border-color);
      }
      
      .tech {
        font-size: 11px;
      }
    }
    
    .center-section {
      font-size: 11px;
    }
    
    .right-section {
      .status {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        background: var(--el-bg-color);
        border-radius: 12px;
        border: 1px solid var(--el-border-color-light);
        
        .status-dot {
          width: 8px;
          height: 8px;
          background: var(--el-color-success);
          border-radius: 50%;
          animation: pulse 2s infinite;
        }
        
        .status-text {
          font-size: 11px;
          font-weight: 500;
          color: var(--el-color-success);
        }
      }
    }
  }
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.7;
    transform: scale(1.1);
  }
}

// 暗黑模式适配
.dark {
  .footer_box {
    background: var(--el-fill-color-dark);
    border-top-color: var(--el-border-color-darker);
    
    .footer-content {
      .right-section {
        .status {
          background: var(--el-bg-color-page);
          border-color: var(--el-border-color-darker);
        }
      }
    }
  }
}
</style>
