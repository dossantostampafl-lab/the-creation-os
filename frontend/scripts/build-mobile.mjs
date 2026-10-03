import { spawnSync } from 'node:child_process';
const endpoint = process.env.CREATION_MOBILE_API_URL ?? 'https://148-116-109-255.sslip.io/api/v1';
const url = new URL(endpoint);
if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) {
  throw new Error('CREATION_MOBILE_API_URL must be HTTPS without credentials or query');
}
for (const [command, args] of [['npm',['run','build']],['npx',['cap','sync']]]) {
  const result=spawnSync(command,args,{stdio:'inherit',env:{...process.env,VITE_API_BASE_URL:endpoint}});
  if (result.status !== 0) process.exit(result.status ?? 1);
}
