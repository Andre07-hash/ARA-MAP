/* Individual sign-in and the session's lifecycle.
 *
 * Every team member signs in as themselves; all of them can do the same
 * things. Ending a session (logout, or a 401 from the server) runs the app's
 * `onSignedOut`, which cancels private requests and clears private state.
 */

import { api, onSessionExpired } from "../../lib/api.js";
import { el } from "../../lib/dom.js";
import { getState, setState } from "../../lib/store.js";
import { openDialog } from "../ui/dialog.js";
import { toast, toastError } from "../ui/toast.js";

export function createSession({ onSignedIn, onSignedOut, hasUnsavedWork }) {
  let dialogoAbierto = null;

  /** Ask the server who we are. Returns the user, or null. */
  async function refresh() {
    const antes = getState().sesion;
    let usuario = null;
    try {
      const respuesta = await api.session();
      usuario = respuesta?.authenticated ? respuesta.user : null;
    } catch (error) {
      // Unknown is not anonymous: keep the current state and say so.
      if (!getState().sesionLista) setState({ sesionLista: true });
      toastError(`No se pudo comprobar la sesión: ${error.message}`);
      return antes;
    }
    setState({ sesion: usuario, sesionLista: true });
    if (antes && !usuario) expired({ silencioso: false });
    else if (!antes && usuario) onSignedIn(usuario, { returnTo: null, startup: true });
    return usuario;
  }

  /** The sign-in dialog. `returnTo` is where to go once signed in. */
  function signIn({ returnTo = null, motivo = null, onCancel = null } = {}) {
    if (dialogoAbierto) return;
    const usuario = el("input", {
      id: "login-usuario", class: "input", autocomplete: "username", required: true,
      autocapitalize: "none", spellcheck: "false",
    });
    const clave = el("input", {
      id: "login-clave", type: "password", class: "input", autocomplete: "current-password", required: true,
    });
    const error = el("p", { class: "field-error", role: "alert" });
    const entrar = el("button", { type: "submit", class: "btn btn-principal" }, "Entrar");
    let entro = false;

    const form = el("form", { class: "login-form" },
      el("div", { class: "rail-field" },
        el("label", { class: "field-label", for: "login-usuario" }, "Usuario"), usuario),
      el("div", { class: "rail-field" },
        el("label", { class: "field-label", for: "login-clave" }, "Contraseña"), clave),
      error,
      entrar,
    );

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      error.textContent = "";
      if (!usuario.value.trim() || !clave.value) {
        error.textContent = "Escribe tu usuario y tu contraseña.";
        return;
      }
      entrar.disabled = true;
      try {
        await api.login(usuario.value.trim(), clave.value);
        const respuesta = await api.session();
        if (!respuesta?.authenticated) throw new Error("El servidor no confirmó la sesión.");
        entro = true;
        dialogoAbierto?.close();
        setState({ sesion: respuesta.user, sesionLista: true });
        toast(`Hola, ${respuesta.user.display_name}.`);
        onSignedIn(respuesta.user, { returnTo, startup: false });
      } catch (e) {
        error.textContent = e.status === 429
          ? "Demasiados intentos. Espera un momento y vuelve a intentarlo."
          : e.status === 401 || e.status === 422 || e.status === 400
            ? (e.message && !/^Error \d+$/.test(e.message) ? e.message : "Usuario o contraseña incorrectos.")
            : e.message;
        clave.value = "";
        clave.focus();
      } finally {
        entrar.disabled = false;
      }
    });

    const { dialog, close } = openDialog({
      titulo: "Iniciar sesión",
      descripcion: motivo ?? "Acceso para el equipo. Cada persona entra con su propio usuario.",
      ancho: "26rem",
      contenido: form,
      acciones: [{ etiqueta: "Cancelar", onClick: (cerrar) => cerrar() }],
    });
    dialogoAbierto = { close };
    dialog.addEventListener("close", () => {
      dialogoAbierto = null;
      if (!entro) onCancel?.();
    });
  }

  /** The server says the session is gone (expired, revoked, signed out elsewhere). */
  function expired({ silencioso = false } = {}) {
    const returnTo = getState().ruta;
    if (hasUnsavedWork()) {
      // Keep the form: sign in again to save it. Giving up clears everything.
      signIn({
        returnTo,
        motivo: "Tu sesión terminó. Vuelve a entrar para guardar; lo que escribiste sigue en pantalla.",
        onCancel: () => { if (!getState().sesion) onSignedOut(); },
      });
      setState({ sesion: null });
      return;
    }
    onSignedOut();
    if (!silencioso) toastError("Tu sesión terminó. Inicia sesión de nuevo para ver el inventario.");
    signIn({ returnTo });
  }

  async function signOut() {
    onSignedOut();
    try {
      await api.logout();
      toast("Sesión cerrada.");
    } catch (error) {
      toastError("La pantalla ya no muestra datos del equipo, pero el servidor no confirmó el " +
        `cierre de sesión (${error.message}). En un equipo compartido, cierra el navegador.`);
    }
  }

  onSessionExpired(() => {
    if (getState().sesion) expired();
  });

  return { refresh, signIn, signOut, expired };
}
