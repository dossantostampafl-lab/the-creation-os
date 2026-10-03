import { Capacitor } from '@capacitor/core';
import { App as NativeApp } from '@capacitor/app';
import { Haptics, ImpactStyle } from '@capacitor/haptics';

export const NATIVE_BACKGROUND_EVENT = 'creation-native-background';

export async function installNativeRuntime(): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;
  await NativeApp.addListener('appStateChange', ({ isActive }) => {
    if (!isActive) window.dispatchEvent(new Event(NATIVE_BACKGROUND_EVENT));
  });
  document.addEventListener('click', (event) => {
    if ((event.target as Element | null)?.closest('button')) {
      void Haptics.impact({ style: ImpactStyle.Light }).catch(() => undefined);
    }
  });
}
