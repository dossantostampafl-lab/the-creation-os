import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.thecreationos.app',
  appName: 'Creation OS',
  webDir: 'dist',
  server: { hostname: 'localhost', androidScheme: 'https' },
  android: { allowMixedContent: false },
  ios: { contentInset: 'automatic', allowsLinkPreview: false },
};
export default config;
