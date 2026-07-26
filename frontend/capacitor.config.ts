import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'ai.wildlens.nature',
  appName: '识境',
  webDir: 'dist',
  server: {
    androidScheme: 'http',
    cleartext: true,
  },
  plugins: {
    Camera: {
      promptLabelHeader: '拍摄自然照片',
      promptLabelPhoto: '从相册选择',
      promptLabelPicture: '使用相机拍摄',
    },
    StatusBar: {
      style: 'DARK',
      backgroundColor: '#06130f',
    },
  },
}

export default config
