import { useEffect, useState } from 'react';
import { downloadBuild, fetchBuilds } from './buildsApi';
import type { BuildFile, BuildsSnapshot } from './buildsApi';

export function BuildsPanel() {
  const [snapshot, setSnapshot] = useState<BuildsSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setSnapshot(null);
    void fetchBuilds(controller.signal).then(result => {
      if (!controller.signal.aborted) setSnapshot(result);
    }).catch(cause => {
      if (!controller.signal.aborted) setError(cause instanceof Error && cause.message === 'AUTH_REQUIRED'
        ? 'Sua sessão expirou. Entre novamente para baixar os arquivos.'
        : 'Não foi possível verificar os arquivos publicados. Tente novamente.');
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [reload]);
  async function download(file: BuildFile) {
    setDownloading(file.id); setError(''); setMessage('');
    try {
      await downloadBuild(file);
      setMessage(`Download de ${file.filename} iniciado após verificar tamanho e SHA-256.`);
    } catch (cause) {
      setError(cause instanceof Error && cause.message === 'AUTH_REQUIRED'
        ? 'Sua sessão expirou. Entre novamente para baixar os arquivos.'
        : 'O download falhou ou o arquivo não passou na verificação de integridade. Tente novamente.');
    } finally { setDownloading(null); }
  }
  return <section aria-label="Downloads Android">
    <h3>Downloads Android</h3>
    <p>Arquivos publicados no servidor. Baixar não consome créditos de IA.</p>
    <button disabled={loading || downloading !== null} onClick={() => setReload(value => value + 1)}>Atualizar arquivos</button>
    {loading && <p role="status">Verificando arquivos publicados…</p>}
    {error && <p role="alert">{error}</p>}
    {snapshot?.status === 'not_configured' && <p>Nenhum arquivo publicado no servidor. Os downloads aparecerão após a publicação dos builds.</p>}
    {snapshot?.status === 'available' && <>
      <p>Versão: {snapshot.version}</p>
      <div className="stack">{snapshot.files.map(file => <article key={file.id}>
        <strong>{file.title}</strong>
        <p>{file.variant === 'debug' ? 'Debug para testes; não é uma versão de produção.' : 'Release sem assinatura de produção; requer assinatura antes da distribuição.'}</p>
        {file.type === 'aab' && <p>Bundle AAB para publicação; não é instalável diretamente no Android.</p>}
        <p>{file.filename} · {file.size_bytes.toLocaleString('pt-BR')} bytes</p>
        <p style={{ overflowWrap: 'anywhere' }}>SHA-256: <code>{file.sha256}</code></p>
        <button disabled={downloading !== null} onClick={() => void download(file)}>
          {downloading === file.id ? 'Baixando e verificando…' : `Baixar ${file.title}`}
        </button>
      </article>)}</div>
    </>}
    {message && <p role="status">{message}</p>}
  </section>;
}
