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
 */

import { ErrorArchivos, LIMITE_BYTES, comprobar, mensajeDe, nuevaClave, sha256Hex,
  validarArchivoLocal } from "../../lib/archivos.js";

export const FASE = Object.freeze({
  LEYENDO: "leyendo",            // reading the file and computing its SHA-256
  INICIANDO: "iniciando",
  SUBIENDO: "subiendo",          // the PUT is in flight (no byte progress available)
  COMPLETANDO: "completando",    // verification and, for KMZ, the parser (may take seconds)
  LISTO: "listo",                // stored; PDF current, or KMZ boundary active
  REQUIERE_SELECCION: "requiere_seleccion",
  NO_APLICADA: "no_aplicada",    // stored, but another change won (superada / retirado)
  RECHAZADO: "rechazado",        // KMZ stored, parser found no usable boundary
  FALLIDO: "fallido",            // a known failure; `codigo` says which
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

/**
 * crearSubida({cliente, terrenoId, tipo, archivo, alCambiar, turno, ahora})
 *
 * `turno` serializes the expensive part (reading, hashing, PUT): at most one
 * pipeline per widgets factory. It is {intentar() -> boolean, liberar()}.
 * `pendiente` resumes an own pending version found after a reload (no File).
 */
export function crearSubida({ cliente, terrenoId, tipo, archivo = null, pendiente = null,
  alCambiar = () => {}, alServidor = () => {}, turno = null, ahora = () => Date.now() }) {
  const clave = nuevaClave();
  let datos = null;            // the exact start body sent with `clave`
  let inicio = pendiente ? { version_id: pendiente.id, archivo_id: pendiente.archivo_id,
    tamano_declarado: pendiente.tamano_declarado, subida_vence_en: pendiente.subida_vence_en ?? null,
    completar_antes_de: pendiente.completar_antes_de ?? null, nombre_original: pendiente.nombre_original } : null;
  let paso = pendiente ? "contenido" : "leer";
  let actual = null;           // AbortController of the step in flight
  let ocupado = false;
  let muerta = false;
  let tieneTurno = false;
  let estado = {
    fase: pendiente ? FASE.REQUIERE_ARCHIVO : FASE.LEYENDO,
    codigo: null, mensaje: pendiente ? "Elige de nuevo el mismo archivo para continuar esta subida." : "",
    nombre: archivo?.name ?? pendiente?.nombre_original ?? "", tipo,
    versionId: inicio?.version_id ?? null, archivoId: inicio?.archivo_id ?? null,
    reintentable: false, cancelable: Boolean(pendiente), reintentarDesde: null,
    limpiezaPendiente: false, resultado: null, venceEn: inicio?.subida_vence_en ?? null,
  };

  function poner(cambios) {
    if (muerta) return;
    estado = { ...estado, ...cambios };
    alCambiar(estado);
  }

  function soltarTurno() {
    if (tieneTurno) { tieneTurno = false; turno?.liberar(); }
  }

  /* Classify a completion result (fresh or replayed). */
  function terminar(r) {
    const version = r?.version ?? {};
    const comun = { versionId: version.id ?? estado.versionId, archivoId: r?.archivo?.id ?? estado.archivoId,
      resultado: r, limpiezaPendiente: Boolean(r?.limpieza_pendiente), reintentable: false,
      cancelable: false, reintentarDesde: null };
    paso = "hecho";
    if (version.estado === "fallido") {
      const codigo = version.error?.codigo ?? "fallido";
      return poner({ ...comun, fase: FASE.FALLIDO, codigo,
        mensaje: version.error?.mensaje ?? mensajeDe(codigo, "El archivo no pasó la verificación.") });
    }
    if (version.estado === "cancelado") return poner({ ...comun, fase: FASE.CANCELADO, codigo: null, mensaje: "Subida cancelada." });
    if (version.estado === "expirado") return poner({ ...comun, fase: FASE.EXPIRADO, codigo: "subida_expirada", mensaje: "El plazo de esta subida venció." });
    if (version.estado !== "disponible") {
      return poner({ ...comun, fase: FASE.INCIERTO, codigo: "respuesta_ilegible",
        mensaje: mensajeDe("respuesta_ilegible"), reintentable: true });
    }
    if (tipo === "pdf") {
      return poner({ ...comun, fase: FASE.LISTO, codigo: null, mensaje: "PDF guardado." });
    }
    const resultado = r?.intento?.resultado;
    if (resultado === "listo" && r?.aplicada) {
      return poner({ ...comun, fase: FASE.LISTO, codigo: null, mensaje: "KMZ guardado; su contorno es el activo." });
    }
    if (resultado === "listo") {
      const motivo = r?.motivo_no_aplicada;
      return poner({ ...comun, fase: FASE.NO_APLICADA, codigo: motivo ?? "no_aplicada",
        mensaje: motivo === "retirado"
          ? "KMZ guardado, pero el archivo fue retirado mientras se procesaba; no se activó."
          : "KMZ guardado, pero otro cambio llegó antes; el contorno activo no cambió. Puedes activarlo desde las versiones." });
    }
    if (resultado === "requiere_seleccion") {
      return poner({ ...comun, fase: FASE.REQUIERE_SELECCION, codigo: null,
        mensaje: "El KMZ tiene varios contornos. Elige cuáles forman el terreno y luego actívalo." });
    }
    return poner({ ...comun, fase: FASE.RECHAZADO, codigo: r?.intento?.resultado ?? "rechazado",
      mensaje: "El KMZ se guardó, pero no tiene un contorno utilizable. El contorno activo no cambió." });
  }

  /* Map a failed step to a state. `donde` is the step that failed. */
  function fallar(error, donde) {
    paso = donde;
    if (!(error instanceof ErrorArchivos)) {
      return poner({ fase: FASE.FALLIDO, codigo: "error", mensaje: "No se pudo completar la subida.",
        reintentable: false, cancelable: Boolean(inicio) });
    }
    const base = { codigo: error.codigo, mensaje: error.message, cancelable: Boolean(inicio) || donde === "iniciar",
      reintentarDesde: null };
    if (error.incierto) return poner({ ...base, fase: FASE.INCIERTO, reintentable: true });
    switch (error.codigo) {
      case "procesamiento_en_curso":
      case "lease_perdido": {
        const s = error.reintentarDespuesDe ?? 5;
        return poner({ ...base, fase: FASE.EN_CURSO, reintentable: true, reintentarDesde: ahora() + s * 1000,
          mensaje: `Otro proceso está trabajando con este archivo. Podrás reintentar en ${s} s.` });
      }
      case "contenido_temporal_ausente":
        paso = "contenido";
        return poner({ ...base, fase: FASE.FALLIDO, reintentable: Boolean(archivo),
          mensaje: "El servidor no tiene el contenido de esta subida. Reintenta para volver a enviarlo." });
      case "almacen_no_disponible":
        return poner({ ...base, fase: FASE.FALLIDO, reintentable: true,
          limpiezaPendiente: Boolean(error.detalle?.limpieza_pendiente) });
      case "subida_expirada":
        paso = "hecho";
        return poner({ ...base, fase: FASE.EXPIRADO, reintentable: false, cancelable: false });
      case "subida_no_pendiente":
        // The version is no longer accepting content: learn its real outcome.
        paso = "completar";
        return poner({ ...base, fase: FASE.INCIERTO, reintentable: true,
          mensaje: "Esta subida ya no acepta contenido. Reintenta para ver su resultado." });
      default:
        paso = donde === "iniciar" ? "iniciar" : "hecho";
        return poner({ ...base, fase: FASE.FALLIDO, reintentable: false,
          cancelable: Boolean(inicio) && error.status !== 404 });
    }
  }

  async function paso_leer(senal) {
    poner({ fase: FASE.LEYENDO, mensaje: "Calculando la huella del archivo…", reintentable: false });
    const invalido = validarArchivoLocal(archivo, tipo);
    if (invalido) throw invalido;
    let bytes = await archivo.arrayBuffer();
    comprobar(senal);
    if (bytes.byteLength !== archivo.size || bytes.byteLength > LIMITE_BYTES[tipo]) {
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
    alServidor();
  }

  async function paso_contenido(senal) {
    poner({ fase: FASE.SUBIENDO, mensaje: "Enviando el archivo…", reintentable: false, cancelable: true });
    await cliente.subir(inicio.version_id, tipo, archivo, { signal: senal });
    comprobar(senal);
    paso = "completar";
  }

  async function paso_completar(senal) {
    poner({ fase: FASE.COMPLETANDO, mensaje: tipo === "kmz"
      ? "Verificando y procesando el KMZ (puede tardar unos segundos)…" : "Verificando el archivo…",
    reintentable: false, cancelable: false });
    const r = await cliente.completar(inicio.version_id, { signal: senal });
    comprobar(senal);
    terminar(r);
    alServidor();
  }

  const PASOS = { leer: paso_leer, iniciar: paso_iniciar, contenido: paso_contenido, completar: paso_completar };

  /* Run from the current step until a terminal state or a failure. Never throws. */
  async function ejecutar() {
    if (ocupado || muerta || paso === "hecho") return;
    if (estado.reintentarDesde && ahora() < estado.reintentarDesde) return;
    if (paso === "contenido" && !archivo) {
      return poner({ fase: FASE.REQUIERE_ARCHIVO, reintentable: false, cancelable: Boolean(inicio),
        mensaje: "Elige de nuevo el mismo archivo para continuar esta subida." });
    }
    // The whole pipeline (read, hash, PUT, completion) holds the factory's one turn.
    if (turno && !tieneTurno) {
      if (!turno.intentar()) {
        poner({ mensaje: "Otra subida está en curso. Inténtalo cuando termine.", reintentable: true });
        return;
      }
      tieneTurno = true;
    }
    ocupado = true;
    try {
      while (!muerta && PASOS[paso]) {
        const donde = paso;
        actual = new AbortController();
        try {
          await PASOS[donde](actual.signal);
        } catch (error) {
          if (esAbort(error) || muerta) return;
          fallar(error, donde);
          return;
        } finally {
          actual = null;
        }
      }
    } finally {
      ocupado = false;
      soltarTurno();
    }
  }

  return {
    estado: () => estado,
    clave,
    ejecutar,
    async reintentar() {
      if (!estado.reintentable || muerta) return;
      await ejecutar();
    },
    /** A reloaded pending upload: the same version, from a newly chosen file. */
    async elegirArchivo(nuevo) {
      if (muerta || paso !== "contenido" || archivo) return;
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
    /** Explicit cancellation through the server; reports what it answered. */
    async cancelar() {
      if (muerta || esTerminal(estado.fase) || estado.fase === FASE.CANCELANDO) return;
      actual?.abort();                             // stop local work first
      while (ocupado) await new Promise((r) => setTimeout(r, 0));
      if (!inicio && paso === "iniciar" && datos && estado.fase === FASE.INCIERTO) {
        // The start may have reached the server: resolve it with the same key first.
        try {
          inicio = await cliente.iniciar(terrenoId, datos, clave);
          poner({ versionId: inicio.version_id, archivoId: inicio.archivo_id });
        } catch (error) {
          if (error instanceof ErrorArchivos && !error.incierto) { inicio = null; }
          else return poner({ fase: FASE.INCIERTO, mensaje: "No se pudo confirmar si la subida llegó a registrarse; no se canceló.", reintentable: true });
        }
      }
      if (!inicio) {
        paso = "hecho";
        soltarTurno();
        return poner({ fase: FASE.CANCELADO, codigo: null, mensaje: "Subida cancelada antes de registrarse.", cancelable: false, reintentable: false });
      }
      const previo = estado.fase;
      poner({ fase: FASE.CANCELANDO, mensaje: "Cancelando…", reintentable: false });
      try {
        const r = await cliente.cancelar(inicio.version_id);
        if (muerta) return;
        paso = "hecho";
        poner({ fase: FASE.CANCELADO, codigo: null, cancelable: false, reintentable: false,
          limpiezaPendiente: Boolean(r?.limpieza_pendiente),
          mensaje: r?.limpieza_pendiente ? "Subida cancelada. El servidor terminará de limpiar el contenido temporal."
            : "Subida cancelada." });
        alServidor();
      } catch (error) {
        if (esAbort(error) || muerta) return;
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
    },
    /** Local teardown (destroy/reset). The server is not asked to do anything. */
    abortar() {
      muerta = true;
      actual?.abort();
      soltarTurno();
      archivo = null;
      datos = null;
    },
  };
}
