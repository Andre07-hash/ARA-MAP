/* One logical upload: hash → start → raw PUT → complete, as a state machine.
 *
 * No DOM. The widget renders `estado()` and calls the methods. The rules this
 * encodes are the accepted lifecycle's (Round 1 contract, 2B routes):
 *
 * - One idempotency key per logical upload, reused only with the same body:
 *   an ambiguous start is resolved by replaying it with that key, never by
 *   starting another version.
 * - An ambiguous completion is resolved by calling completion again: a
 *   terminal version replays its stored outcome.
 * - Content is re-staged only for the same version, from the same File,
 *   while the server still accepts it.
 * - Nothing retries by itself. Every retry is a user action, and a server
 *   "retry after" hint holds the retry back until then.
 * - Cancelling local work proves nothing about the server: an explicit
 *   cancellation calls the cancel endpoint and reports what it answered.
 * - Everything this upload sends, including an explicit cancellation and the
 *   start replay before it, belongs to its lifetime: after abortar() nothing
 *   more is sent and nothing is reported (Round 3 review R3-B1).
 * - Only a confirmed outcome is terminal. A failed step while the server
 *   version is still pending stays counted, cancellable and, where safe,
 *   retryable (R3-B3).
 * - Losing the scope (404) or the right to write (403) ends the upload here and is handed to the host through
 *   `alPerderAcceso`, so private state is cleared and the record revalidated
 *   (R3-B2).
 */

import { ErrorArchivos, comprobar, formatoDe, limiteArchivo, mensajeDe, nombreFormato, nuevaClave,
  sha256Hex, validarArchivoLocal } from "../../lib/archivos.js";

export const FASE = Object.freeze({
  LEYENDO: "leyendo",            // reading the file and computing its SHA-256
  INICIANDO: "iniciando",
  SUBIENDO: "subiendo",          // the PUT is in flight (no byte progress available)
  COMPLETANDO: "completando",    // verification and, for KMZ/KML, the parser (may take seconds)
  LISTO: "listo",                // stored; PDF current, or KMZ/KML boundary active
  REQUIERE_SELECCION: "requiere_seleccion",
  NO_APLICADA: "no_aplicada",    // stored, but another change won (superada / retirado)
  RECHAZADO: "rechazado",        // KMZ/KML stored, parser found no usable boundary
  FALLIDO: "fallido",            // a known failure; `codigo` says which
  INTERRUMPIDO: "interrumpido",  // a step failed; the server version is still pending
  INCIERTO: "incierto",          // the last reply never arrived: retry resolves it safely
  EN_CURSO: "en_curso",          // another process holds the version (lease)
  EXPIRADO: "expirado",
  REQUIERE_ARCHIVO: "requiere_archivo",   // a pending upload found after reload: choose the file again
  CANCELANDO: "cancelando",
  CANCELADO: "cancelado",
});

const TERMINALES = new Set([FASE.LISTO, FASE.REQUIERE_SELECCION, FASE.NO_APLICADA, FASE.RECHAZADO,
  FASE.FALLIDO, FASE.EXPIRADO, FASE.CANCELADO]);

export const esTerminal = (fase) => TERMINALES.has(fase);

const esAbort = (e) => e?.name === "AbortError";

/* The server's answer means this account may no longer act on the terrain:
 * gone from its scope (404, indistinguishable from missing), or still visible
 * but not writable (403). */
const ACCESO_PERDIDO = new Set(["forbidden"]);
export const pierdeAcceso = (e) => e instanceof ErrorArchivos
  && (e.status === 404 || e.status === 403 || (e.status === 409 && ACCESO_PERDIDO.has(e.codigo)));

/* The version states a completion reply may report, and the KMZ attempt
 * results that resolve one. Anything else is an unreadable outcome. */
const ESTADOS_FINALES = new Set(["disponible", "fallido", "cancelado", "expirado"]);
const RESULTADOS_KMZ = new Set(["listo", "requiere_seleccion", "rechazado", "error_interno"]);

/**
 * The factory's single read/hash/upload pipeline. A permit is an object, so a
 * stale holder can never release somebody else's (R3-B4).
 *   intentar() -> permit | null;  liberar(permit);  ocupado() -> boolean
 */
export function crearTurno() {
  let actual = null;
  return {
    intentar() {
      if (actual) return null;
      actual = {};
      return actual;
    },
    liberar(permiso) { if (permiso && permiso === actual) actual = null; },
    ocupado: () => actual !== null,
  };
}

/**
 * crearSubida({cliente, terrenoId, tipo, archivo, alCambiar, turno, ahora})
 *
 * `turno` serializes the expensive part (reading, hashing, PUT): at most one
 * pipeline per widgets factory (crearTurno). The permit is held until the
 * running step has settled, even after abortar(): a file read or a digest
 * cannot be cancelled, only waited for.
 * `pendiente` resumes an own pending version found after a reload (no File).
 * `alPerderAcceso(error)` is called once when the server says this account
 * lost the terrain or the right to write it.
 */
export function crearSubida({ cliente, terrenoId, tipo, archivo = null, pendiente = null,
  alCambiar = () => {}, alServidor = () => {}, alPerderAcceso = () => {}, turno = null,
  ahora = () => Date.now() }) {
  const clave = nuevaClave();
  let datos = null;            // the exact start body sent with `clave`
  let inicio = pendiente ? { version_id: pendiente.id, archivo_id: pendiente.archivo_id,
    tamano_declarado: pendiente.tamano_declarado, subida_vence_en: pendiente.subida_vence_en ?? null,
    completar_antes_de: pendiente.completar_antes_de ?? null, nombre_original: pendiente.nombre_original } : null;
  let paso = pendiente ? "contenido" : "leer";
  let actual = null;           // AbortController of the step in flight
  let corriendo = null;        // the running ejecutar(), until its step has settled
  let cancelando = false;
  let permiso = null;          // the pipeline permit this upload holds
  const vida = new AbortController();      // this upload's lifetime: abortar() ends it
  const muerta = () => vida.signal.aborted;
  let estado = {
    fase: pendiente ? FASE.REQUIERE_ARCHIVO : FASE.LEYENDO,
    codigo: null, mensaje: pendiente ? "Elige de nuevo el mismo archivo para continuar esta subida." : "",
    nombre: archivo?.name ?? pendiente?.nombre_original ?? "", tipo,
    versionId: inicio?.version_id ?? null, archivoId: inicio?.archivo_id ?? null,
    reintentable: false, cancelable: Boolean(pendiente), reintentarDesde: null,
    limpiezaPendiente: false, resultado: null, venceEn: inicio?.subida_vence_en ?? null,
  };

  function poner(cambios) {
    if (muerta()) return;
    estado = { ...estado, ...cambios };
    alCambiar(estado);
  }

  const avisarServidor = () => { if (!muerta()) alServidor(); };

  function soltarTurno() {
    if (permiso) { const p = permiso; permiso = null; turno?.liberar(p); }
  }

  /* The server ended this account's access: stop here and tell the host. */
  function accesoPerdido(error) {
    paso = "hecho";
    const fuera = error.status === 404;
    poner({ fase: FASE.FALLIDO, codigo: fuera ? "no_encontrado" : error.codigo,
      mensaje: fuera ? "Este terreno ya no está disponible para tu cuenta." : error.message,
      reintentable: false, cancelable: false, reintentarDesde: null });
    if (!muerta()) alPerderAcceso(error);
  }

  /* Whether a completion reply states a resolved outcome. */
  function resuelto(r) {
    const v = r?.version;
    if (!v || typeof v !== "object" || !ESTADOS_FINALES.has(v.estado)) return false;
    if (v.estado !== "disponible" || tipo !== "kmz") return true;
    return RESULTADOS_KMZ.has(r?.intento?.resultado);
  }

  /* Classify a completion result (fresh or replayed). */
  function terminar(r) {
    const version = r?.version ?? {};
    const comun = { versionId: version.id ?? estado.versionId, archivoId: r?.archivo?.id ?? estado.archivoId,
      resultado: r, limpiezaPendiente: Boolean(r?.limpieza_pendiente), reintentable: false,
      cancelable: false, reintentarDesde: null };
    paso = "hecho";             // only called with a resolved outcome (see resuelto)
    if (version.estado === "fallido") {
      const codigo = version.error?.codigo ?? "fallido";
      return poner({ ...comun, fase: FASE.FALLIDO, codigo,
        mensaje: version.error?.mensaje ?? mensajeDe(codigo, "El archivo no pasó la verificación.") });
    }
    if (version.estado === "cancelado") return poner({ ...comun, fase: FASE.CANCELADO, codigo: null, mensaje: "Subida cancelada." });
    if (version.estado === "expirado") return poner({ ...comun, fase: FASE.EXPIRADO, codigo: "subida_expirada", mensaje: "El plazo de esta subida venció." });
    if (tipo === "pdf") {
      return poner({ ...comun, fase: FASE.LISTO, codigo: null, mensaje: "Archivo guardado." });
    }
    const resultado = r?.intento?.resultado;
    // The file's real format (KMZ or KML), never a KML presented as a KMZ.
    const f = nombreFormato(formatoDe(version.nombre_original ?? estado.nombre, tipo));
    if (resultado === "listo" && r?.aplicada) {
      return poner({ ...comun, fase: FASE.LISTO, codigo: null, mensaje: `${f} guardado; su contorno es el activo.` });
    }
    if (resultado === "listo") {
      const motivo = r?.motivo_no_aplicada;
      return poner({ ...comun, fase: FASE.NO_APLICADA, codigo: motivo ?? "no_aplicada",
        mensaje: motivo === "retirado"
          ? `${f} guardado, pero el archivo fue retirado mientras se procesaba; no se activó.`
          : `${f} guardado, pero otro cambio llegó antes; el contorno activo no cambió. Puedes activarlo desde las versiones.` });
    }
    if (resultado === "requiere_seleccion") {
      return poner({ ...comun, fase: FASE.REQUIERE_SELECCION, codigo: null,
        mensaje: `El ${f} tiene varios contornos. Elige cuáles forman el terreno y luego actívalo.` });
    }
    return poner({ ...comun, fase: FASE.RECHAZADO, codigo: r?.intento?.resultado ?? "rechazado",
      mensaje: `El ${f} se guardó, pero no tiene un contorno utilizable. El contorno activo no cambió.` });
  }

  /* Map a failed step to a state. `donde` is the step that failed. A version
   * the server still holds as pending is never shown as terminal. */
  function fallar(error, donde) {
    paso = donde;
    const pendienteEnServidor = Boolean(inicio);
    if (!(error instanceof ErrorArchivos)) {
      if (pendienteEnServidor) {
        return poner({ fase: FASE.INTERRUMPIDO, codigo: "error", mensaje: "No se pudo completar la subida.",
          reintentable: false, cancelable: true, reintentarDesde: null });
      }
      paso = "hecho";
      return poner({ fase: FASE.FALLIDO, codigo: "error", mensaje: "No se pudo completar la subida.",
        reintentable: false, cancelable: false });
    }
    if (pierdeAcceso(error)) return accesoPerdido(error);
    const base = { codigo: error.codigo, mensaje: error.message, cancelable: pendienteEnServidor || donde === "iniciar",
      reintentarDesde: null };
    // A lost or unreadable reply (an oversized one included): the server may have acted.
    if (error.incierto || error.codigo === "respuesta_excesiva") {
      return poner({ ...base, fase: FASE.INCIERTO, reintentable: true });
    }
    switch (error.codigo) {
      case "procesamiento_en_curso":
      case "lease_perdido": {
        const s = error.reintentarDespuesDe ?? 5;
        return poner({ ...base, fase: FASE.EN_CURSO, reintentable: true, reintentarDesde: ahora() + s * 1000,
          mensaje: `Otro proceso está trabajando con este archivo. Podrás reintentar en ${s} s.` });
      }
      case "contenido_temporal_ausente":
        // The version is pending without its bytes: send them again, or cancel it.
        paso = "contenido";
        return poner({ ...base, fase: FASE.INTERRUMPIDO, reintentable: Boolean(archivo), cancelable: true,
          mensaje: archivo ? "El servidor no tiene el contenido de esta subida. Reintenta para volver a enviarlo."
            : "El servidor no tiene el contenido de esta subida. Elige de nuevo el archivo o cancélala." });
      case "almacen_no_disponible": {
        const s = error.reintentarDespuesDe;
        return poner({ ...base, fase: FASE.INTERRUMPIDO, reintentable: true,
          reintentarDesde: s ? ahora() + s * 1000 : null,
          limpiezaPendiente: Boolean(error.detalle?.limpieza_pendiente) });
      }
      case "subida_expirada":
        paso = "hecho";
        return poner({ ...base, fase: FASE.EXPIRADO, reintentable: false, cancelable: false });
      case "subida_no_pendiente":
        // The version is no longer accepting content: learn its real outcome.
        paso = "completar";
        return poner({ ...base, fase: FASE.INCIERTO, reintentable: true,
          mensaje: "Esta subida ya no acepta contenido. Reintenta para ver su resultado." });
      default:
        if (pendienteEnServidor) {
          // The step was refused, but the version itself has no outcome yet.
          return poner({ ...base, fase: FASE.INTERRUMPIDO, cancelable: true,
            reintentable: error.status >= 500 });
        }
        // Nothing was registered: the start was refused.
        paso = "hecho";
        return poner({ ...base, fase: FASE.FALLIDO, reintentable: false, cancelable: false });
    }
  }

  async function paso_leer(senal) {
    poner({ fase: FASE.LEYENDO, mensaje: "Calculando la huella del archivo…", reintentable: false });
    const invalido = validarArchivoLocal(archivo, tipo);
    if (invalido) throw invalido;
    let bytes = await archivo.arrayBuffer();
    comprobar(senal);
    if (bytes.byteLength !== archivo.size || bytes.byteLength > limiteArchivo(archivo, tipo)) {
      throw new ErrorArchivos("archivo_grande", mensajeDe("archivo_grande"));
    }
    const sha = await sha256Hex(bytes);
    bytes = null;      // only the File reference stays, for the PUT
    comprobar(senal);
    datos = { tipo, nombre_original: archivo.name, tamano_declarado: archivo.size, sha256_declarado: sha };
    paso = "iniciar";
  }

  async function paso_iniciar(senal) {
    poner({ fase: FASE.INICIANDO, mensaje: "Registrando la subida…", reintentable: false, cancelable: false });
    const r = await cliente.iniciar(terrenoId, datos, clave, { signal: senal });
    comprobar(senal);
    inicio = r;
    paso = "contenido";
    poner({ versionId: r.version_id, archivoId: r.archivo_id, venceEn: r.subida_vence_en ?? null, cancelable: true });
    avisarServidor();
  }

  async function paso_contenido(senal) {
    poner({ fase: FASE.SUBIENDO, mensaje: "Enviando el archivo…", reintentable: false, cancelable: true });
    await cliente.subir(inicio.version_id, tipo, archivo, { signal: senal });
    comprobar(senal);
    paso = "completar";
  }

  async function paso_completar(senal) {
    poner({ fase: FASE.COMPLETANDO, mensaje: tipo === "kmz"
      ? `Verificando y procesando el ${nombreFormato(formatoDe(estado.nombre, tipo))} (puede tardar unos segundos)…`
      : "Verificando el archivo…",
    reintentable: false, cancelable: false });
    const r = await cliente.completar(inicio.version_id, { signal: senal });
    comprobar(senal);
    if (!resuelto(r)) {
      // A reply without its outcome: resolve it by replaying completion, by hand.
      throw new ErrorArchivos("respuesta_ilegible", mensajeDe("respuesta_ilegible"), { incierto: true });
    }
    terminar(r);
    avisarServidor();
  }

  const PASOS = { leer: paso_leer, iniciar: paso_iniciar, contenido: paso_contenido, completar: paso_completar };

  /* Run from the current step until a terminal state or a failure. Never throws.
   * The permit is released only when the step in flight has settled: an
   * aborted fetch settles at once, a file read or digest when it finishes. */
  function ejecutar() {
    if (corriendo || cancelando || muerta() || paso === "hecho") return corriendo ?? Promise.resolve();
    if (estado.reintentarDesde && ahora() < estado.reintentarDesde) return Promise.resolve();
    if (paso === "contenido" && !archivo) {
      poner({ fase: FASE.REQUIERE_ARCHIVO, reintentable: false, cancelable: Boolean(inicio),
        mensaje: "Elige de nuevo el mismo archivo para continuar esta subida." });
      return Promise.resolve();
    }
    // The whole pipeline (read, hash, PUT, completion) holds the factory's one turn.
    if (turno && !permiso) {
      const p = turno.intentar();
      if (!p) {
        poner({ mensaje: "Otra subida está en curso. Inténtalo cuando termine.", reintentable: true });
        return Promise.resolve();
      }
      permiso = p;
    }
    corriendo = (async () => {
      try {
        while (!muerta() && PASOS[paso]) {
          const donde = paso;
          const control = new AbortController();
          actual = control;
          try {
            await PASOS[donde](AbortSignal.any([vida.signal, control.signal]));
          } catch (error) {
            if (esAbort(error) || muerta() || control.signal.aborted) return;
            fallar(error, donde);
            return;
          } finally {
            actual = null;
          }
        }
      } finally {
        corriendo = null;
        soltarTurno();
      }
    })();
    return corriendo;
  }

  /* Wait for the running step to let go; false when this upload ended meanwhile. */
  async function soltarPaso() {
    actual?.abort();                               // stop local work first
    while (corriendo) await corriendo;
    return !muerta();
  }

  return {
    estado: () => estado,
    clave,
    ejecutar,
    async reintentar() {
      if (!estado.reintentable || muerta()) return;
      await ejecutar();
    },
    /** A reloaded pending upload: the same version, from a newly chosen file. */
    async elegirArchivo(nuevo) {
      if (muerta() || paso !== "contenido" || archivo) return;
      const invalido = validarArchivoLocal(nuevo, tipo);
      if (invalido) return poner({ codigo: invalido.codigo, mensaje: invalido.message });
      if (inicio?.tamano_declarado != null && nuevo.size !== inicio.tamano_declarado) {
        return poner({ codigo: "archivo_distinto",
          mensaje: "Ese archivo no es el que se registró para esta subida (el tamaño no coincide)." });
      }
      archivo = nuevo;
      poner({ nombre: inicio?.nombre_original ?? nuevo.name, codigo: null });
      await ejecutar();
    },
    /** Explicit cancellation through the server; reports what it answered.
     * Every request it sends carries this upload's lifetime, and it re-checks
     * that lifetime after every wait: once abortar() ran, it sends nothing. */
    async cancelar() {
      if (muerta() || cancelando || esTerminal(estado.fase) || estado.fase === FASE.CANCELANDO) return;
      cancelando = true;
      try {
        if (!(await soltarPaso())) return;
        const senal = vida.signal;
        if (!inicio && paso === "iniciar" && datos && estado.fase === FASE.INCIERTO) {
          // The start may have reached the server: resolve it with the same key first.
          try {
            inicio = await cliente.iniciar(terrenoId, datos, clave, { signal: senal });
            if (muerta()) return;
            poner({ versionId: inicio.version_id, archivoId: inicio.archivo_id });
          } catch (error) {
            // An abort is teardown, not proof that the start never happened.
            if (esAbort(error) || muerta()) return;
            if (pierdeAcceso(error)) return accesoPerdido(error);
            if (error instanceof ErrorArchivos && !error.incierto) { inicio = null; }
            else return poner({ fase: FASE.INCIERTO, mensaje: "No se pudo confirmar si la subida llegó a registrarse; no se canceló.", reintentable: true });
          }
        }
        if (!inicio) {
          paso = "hecho";
          return poner({ fase: FASE.CANCELADO, codigo: null, mensaje: "Subida cancelada antes de registrarse.", cancelable: false, reintentable: false });
        }
        if (muerta()) return;
        const previo = estado.fase;
        poner({ fase: FASE.CANCELANDO, mensaje: "Cancelando…", reintentable: false });
        try {
          const r = await cliente.cancelar(inicio.version_id, { signal: senal });
          if (muerta()) return;
          paso = "hecho";
          poner({ fase: FASE.CANCELADO, codigo: null, cancelable: false, reintentable: false,
            limpiezaPendiente: Boolean(r?.limpieza_pendiente),
            mensaje: r?.limpieza_pendiente ? "Subida cancelada. El servidor terminará de limpiar el contenido temporal."
              : "Subida cancelada." });
          avisarServidor();
        } catch (error) {
          if (esAbort(error) || muerta()) return;
          if (pierdeAcceso(error)) return accesoPerdido(error);
          if (error instanceof ErrorArchivos && error.codigo === "subida_no_pendiente") {
            // Too late to cancel: it already finished. Show what really happened.
            paso = "completar";
            poner({ fase: FASE.INCIERTO, mensaje: "La subida ya había terminado; no se canceló. Consulta su resultado.", reintentable: true });
            return;
          }
          poner({ fase: previo === FASE.CANCELANDO ? FASE.INCIERTO : previo, codigo: error?.codigo ?? "error",
            mensaje: `No se pudo cancelar: ${error?.message ?? "error desconocido"}`, cancelable: true,
            reintentable: estado.reintentable });
        }
      } finally {
        cancelando = false;
      }
    },
    /** Local teardown (destroy/reset). The server is not asked to do anything,
     * nothing more is sent or reported, and the pipeline permit is released
     * as soon as the step in flight has settled. */
    abortar() {
      vida.abort();
      actual?.abort();
      if (!corriendo) soltarTurno();
      archivo = null;
      datos = null;
    },
  };
}
