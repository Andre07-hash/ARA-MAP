// Independent supervisor probes; no application module is modified.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
if (!process.argv[2]) throw new Error('Pass the exact archived repository directory.');
const root = resolve(process.argv[2]);
const moduleAt = path => import(pathToFileURL(resolve(root, path)));
const { crearSubida } = await moduleAt('web/components/archivos/subida.js');
const { ErrorArchivos } = await moduleAt('web/lib/archivos.js');
const { crearCargadorGeometrias } = await moduleAt('web/lib/cargadorGeometrias.js');

const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const tick = () => new Promise(r => setTimeout(r, 0));
const tid = '11111111-1111-4111-8111-111111111111';
const vid = '22222222-2222-4222-8222-222222222222';
const gid = '33333333-3333-4333-8333-333333333333';
const file = new File(['%PDF-1.4 synthetic'], 'synthetic.pdf');
const output = [];

// Cancellation waits for the PUT to settle. Destruction occurs during that wait.
{
  const entered = deferred(), release = deferred();
  let identity = 'old', cancelCalls = [];
  const upload = crearSubida({ terrenoId: tid, tipo: 'pdf', archivo: file, cliente: {
    iniciar: async () => ({ version_id: vid, archivo_id: gid }),
    subir: async (_v, _t, _f, { signal }) => { entered.resolve(); await release.promise; signal.throwIfAborted(); },
    cancelar: async (_v, options) => { cancelCalls.push({ identity, hasSignal: Boolean(options?.signal) }); return {}; },
  }});
  const running = upload.ejecutar();
  await entered.promise;
  const cancelling = upload.cancelar();
  upload.abortar();
  identity = 'new';
  release.resolve();
  await Promise.all([running, cancelling]);
  output.push({ probe: 'cancel_after_destroy', cancelCalls });
}

// A confirmed temporary-content failure still has a pending, cancellable server version.
{
  let cancels = 0;
  const upload = crearSubida({ terrenoId: tid, tipo: 'pdf', archivo: file, cliente: {
    iniciar: async () => ({ version_id: vid, archivo_id: gid }), subir: async () => ({}),
    completar: async () => { throw new ErrorArchivos('contenido_temporal_ausente', 'Synthetic missing bytes', { status: 409 }); },
    cancelar: async () => { cancels++; return {}; },
  }});
  await upload.ejecutar();
  const before = upload.estado();
  await upload.cancelar();
  output.push({ probe: 'retryable_failure_cannot_cancel', phase: before.fase, retryable: before.reintentable, cancelable: before.cancelable, cancels });
}

// A 200 JSON response whose outcome is missing must be resolved by completion replay.
{
  let completions = 0;
  const upload = crearSubida({ terrenoId: tid, tipo: 'pdf', archivo: file, cliente: {
    iniciar: async () => ({ version_id: vid, archivo_id: gid }), subir: async () => ({}),
    completar: async () => { completions++; return {}; },
  }});
  await upload.ejecutar();
  await upload.reintentar();
  output.push({ probe: 'uncertain_completion_replay', phase: upload.estado().fase, retryable: upload.estado().reintentable, completions });
}

// Destruction must not release the factory hash turn before an unabortable read settles.
{
  let busy = false, active = 0, max = 0;
  const turno = { intentar() { if (busy) return false; busy = true; return true; }, liberar() { busy = false; } };
  const release = deferred(), entered = deferred();
  const slow = { name: 'slow.pdf', size: 1, arrayBuffer: async () => { active++; max = Math.max(max, active); entered.resolve(); await release.promise; active--; return new Uint8Array([1]).buffer; } };
  const fast = { name: 'fast.pdf', size: 1, arrayBuffer: async () => { active++; max = Math.max(max, active); active--; return new Uint8Array([1]).buffer; } };
  const client = { iniciar: async () => { throw new ErrorArchivos('stop', 'Synthetic stop'); } };
  const a = crearSubida({ terrenoId: tid, tipo: 'pdf', archivo: slow, turno, cliente: client });
  const run = a.ejecutar(); await entered.promise; a.abortar();
  const b = crearSubida({ terrenoId: tid, tipo: 'pdf', archivo: fast, turno, cliente: client });
  await b.ejecutar(); release.resolve(); await run;
  output.push({ probe: 'one_hash_pipeline', maxConcurrentReads: max });
}

// The bridge's captured private signal ends while the final digest is pending.
{
  const bytes = Buffer.from(JSON.stringify({ type: 'MultiPolygon', coordinates: [[[[-100,20],[-99,20],[-99,21],[-100,20]]]] }));
  const sha = createHash('sha256').update(bytes).digest('hex');
  const descriptor = { id: gid, archivo_version_id: vid, utilizable: true, bbox: [-100,20,-99,21], punto_interior: { type: 'Point', coordinates: [-99.5,20.2] } };
  const meta = { ...descriptor, terreno_id: tid, activa: true, partes: 1, huecos: 0, vertices: 4, area_aproximada_m2: 1,
    bytes: bytes.length, sha256: sha, fragmento_bytes: 524288, fragmentos: 1 };
  const scope = new AbortController(), entered = deferred(), release = deferred();
  const native = crypto.subtle.digest.bind(crypto.subtle);
  crypto.subtle.digest = async (...args) => { entered.resolve(); await release.promise; return native(...args); };
  const loader = crearCargadorGeometrias({ peticionPrivada: async (path) => ({ signal: scope.signal,
    response: path.endsWith('metadatos') ? Response.json({ geometrias: { [gid]: meta }, no_disponibles: [] }) : new Response(bytes, { headers: {
      'Content-Type': 'application/octet-stream', 'X-Geometria-Id': gid, 'X-Geometria-Desde': '0',
      'X-Geometria-Longitud': String(bytes.length), 'X-Geometria-Bytes': String(bytes.length), 'X-Geometria-Sha256': sha,
      'X-Geometria-Final': '1', 'X-Geometria-Siguiente': 'fin',
    }}),
  })});
  const load = loader.cargar({ terrenoId: tid, geometria: descriptor }).then(() => 'resolved', e => e.name);
  await entered.promise; scope.abort(); release.resolve();
  const result = await load;
  output.push({ probe: 'private_scope_ends_during_digest', result, state: loader.estado() });
  crypto.subtle.digest = native;
  loader.destroy();
}
console.log(JSON.stringify(output, null, 2));
assert.equal(output.length, 5);
