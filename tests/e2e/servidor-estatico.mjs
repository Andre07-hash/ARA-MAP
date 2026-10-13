/* A tiny static server for the B-2 browser harness: the repository root on a
 * random 127.0.0.1 port, plus optional extra routes. No app server, no
 * database, no network. Paths outside the root are refused. */

import { readFile } from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

const TIPOS = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
                '.css': 'text/css', '.json': 'application/json', '.png': 'image/png' };

/** Start serving. `extras` maps a URL path to () => {tipo, cuerpo}. */
export async function servir(extras = {}) {
  const servidor = http.createServer(async (req, res) => {
    const ruta = decodeURIComponent(new URL(req.url, 'http://local').pathname);
    try {
      if (extras[ruta]) {
        const { tipo, cuerpo } = await extras[ruta]();
        res.writeHead(200, { 'Content-Type': tipo });
        res.end(cuerpo);
        return;
      }
      const archivo = path.join(RAIZ, path.normalize(ruta));
      if (!archivo.startsWith(RAIZ + path.sep)) throw new Error('outside root');
      const cuerpo = await readFile(archivo);
      res.writeHead(200, { 'Content-Type': TIPOS[path.extname(archivo)] ?? 'application/octet-stream' });
      res.end(cuerpo);
    } catch {
      res.writeHead(404);
      res.end();
    }
  });
  await new Promise((ok) => servidor.listen(0, '127.0.0.1', ok));
  return { url: `http://127.0.0.1:${servidor.address().port}`, cerrar: () => servidor.close() };
}

/** Chromium: CHROMIUM=/path/to/binary, else the installed "chrome" channel. */
export function opcionesNavegador() {
  return process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : { channel: 'chrome' };
}
