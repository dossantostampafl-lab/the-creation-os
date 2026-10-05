import { authorizedFetch } from './api';

export type BuildFile = {
  id: string; title: string; filename: string; type: 'apk' | 'aab';
  variant: 'debug' | 'release_unsigned'; size_bytes: number; sha256: string;
};
export type BuildsSnapshot = { status: 'available' | 'not_configured'; version: string | null; files: BuildFile[] };

export async function fetchBuilds(signal?: AbortSignal): Promise<BuildsSnapshot> {
  const response = await authorizedFetch('/builds', { signal });
  if (!response.ok) throw new Error(`HTTP_${response.status}`);
  return response.json() as Promise<BuildsSnapshot>;
}

export async function downloadBuild(file: BuildFile): Promise<void> {
  const response = await authorizedFetch(`/builds/${encodeURIComponent(file.id)}/download`);
  if (!response.ok) throw new Error(`HTTP_${response.status}`);
  const blob = await response.blob();
  if (blob.size !== file.size_bytes) throw new Error('BUILD_INTEGRITY_FAILED');
  const digest = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer());
  const sha256 = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
  if (sha256 !== file.sha256) throw new Error('BUILD_INTEGRITY_FAILED');
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = file.filename;
  document.body.append(anchor);
  try { anchor.click(); }
  finally {
    anchor.remove();
    // Give the browser time to consume the download URL before releasing it.
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
