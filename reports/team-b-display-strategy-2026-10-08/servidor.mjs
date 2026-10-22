/* Static server for the display benchmark: three read-only mounts on a
 * random 127.0.0.1 port. No app server, no database, no network.
 *   /b2/     the accepted B-2 renderer, from `git archive 5d8e2dc` (B2_DIR)
 *   /proto/  this report folder (prototype + harness page)
 *   /casos/  the generated fictional cases (CASOS_DIR)
 * Paths that escape a mount are refused. */

import { readFile } from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const TIPOS = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
                '.css': 'text/css', '.json': 'application/json', '.png': 'image/png' };

export async function servir({ b2, casos }) {
  const montajes = { '/b2/': path.resolve(b2), '/proto/': AQUI, '/casos/': path.resolve(casos) };
  const servidor = http.createServer(async (req, res) => {
    const ruta = decodeURIComponent(new URL(req.url, 'http://local').pathname);
    try {
      const prefijo = Object.keys(montajes).find((p) => ruta.startsWith(p));
      if (!prefijo) throw new Error('no mount');
      const raiz = montajes[prefijo];
      const archivo = path.join(raiz, path.normalize(ruta.slice(prefijo.length)));
      if (!archivo.startsWith(raiz + path.sep)) throw new Error('outside mount');
      const cuerpo = await readFile(archivo);
      res.writeHead(200, { 'Content-Type': TIPOS[path.extname(archivo)] ?? 'application/octet-stream',
                           'Cache-Control': 'no-store' });
      res.end(cuerpo);
    } catch {
      res.writeHead(404);
      res.end();
    }
  });
  await new Promise((ok) => servidor.listen(0, '127.0.0.1', ok));
  return { url: `http://127.0.0.1:${servidor.address().port}`, cerrar: () => servidor.close() };
}
