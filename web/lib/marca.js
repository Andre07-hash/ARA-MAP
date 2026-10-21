/* The header logo for whoever is signed in.
 *
 * The server reads the brand stored on the authenticated account
 * (`sesion.marca`, chosen when an administrator creates it); the editable
 * display name plays no part. Anything unknown, and anyone signed
 * out, gets ARA. `nombre` is the written name beside it: «ARA Map» with
 * the ARA mark, just «Map» beside the Dewa wordmark. Width and height are each image's intrinsic size, so the
 * header keeps the supplied proportions and does not shift while it loads.
 */

const LOGOS = {
  ara: { src: "assets/ara-logo.png", width: 522, height: 478, alt: "", clase: "brand-logo",
    nombre: "ARA Map" },
  // The Dewa wordmark is its own name, so it is announced; the ARA mark sits
  // beside the written «ARA Map» and stays decorative.
  dewa: { src: "assets/dewa-logo.png", width: 622, height: 238, alt: "Dewa",
    clase: "brand-logo brand-logo-dewa", nombre: "Map" },
};

export function logoDe(sesion) {
  const marca = sesion?.marca;
  return typeof marca === "string" && Object.hasOwn(LOGOS, marca) ? LOGOS[marca] : LOGOS.ara;
}
