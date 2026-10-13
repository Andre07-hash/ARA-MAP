/* Individual sign-in and the session's lifecycle.
 *
 * Every team member signs in as themselves. Whenever the identity behind this
 * window stops being the one its private content was loaded for (logout, a
 * 401 from the server, or the server now naming another account or another
 * role), the app's `onSignedOut` runs FIRST: it cancels private requests and
 * removes every private row, form, dialog and pending save. Nothing private
 * is kept behind the sign-in dialog, saved or not; only then may a new
 * identity be set.
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
    if (antes && !usuario) {
      expired({ silencioso: false });
      return null;
    }
    // Another account, or another role for this one (a sign-in in another tab
    // shares this cookie): what is on screen belongs to the previous identity.
    const otra = Boolean(antes && usuario && (antes.id !== usuario.id || antes.rol !== usuario.rol));
    const habia = otra && hasUnsavedWork();
    if (otra) onSignedOut();
    setState({ sesion: usuario, sesionLista: true });
    if (usuario && (!antes || otra)) onSignedIn(usuario, { returnTo: null, startup: !antes });
    if (otra) {
      toast(`Esta ventana ahora es de ${usuario.display_name}. Se retiró lo que mostraba la sesión anterior` +
        (habia ? ", incluido lo que estaba sin guardar." : "."));
    }
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
    // Whoever signs in next may be someone else: nothing private waits behind
    // the dialog, unsaved input included. The message says so without quoting it.
    const habia = hasUnsavedWork();
    onSignedOut();
    if (!silencioso || habia) {
      toastError("Tu sesión terminó. Inicia sesión de nuevo para continuar." +
        (habia ? " Lo que estaba sin guardar se descartó." : ""));
    }
    signIn({ returnTo, motivo: habia ? "Tu sesión terminó. Lo que estaba sin guardar se descartó." : null });
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
