/* A very small DOM helper. No framework: this app renders a handful of views
 * and a build step would cost more than it saves. */

/**
 * el("button", { class: "btn", onclick: fn }, "Guardar")
 * Keys starting with "on" bind listeners; everything else becomes an attribute,
 * except `class`, `dataset`, `style` and `html`, which are handled directly.
 */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);

  for (const [key, value] of Object.entries(props ?? {})) {
    if (value == null || value === false) continue;

    if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2), value);
    } else if (key === "class") {
      node.className = Array.isArray(value) ? value.filter(Boolean).join(" ") : value;
    } else if (key === "dataset") {
      Object.assign(node.dataset, value);
    } else if (key === "style" && typeof value === "object") {
      Object.assign(node.style, value);
    } else if (key === "html") {
      node.innerHTML = value; // only ever used with strings this app builds
    } else if (value === true) {
      node.setAttribute(key, "");
    } else {
      node.setAttribute(key, String(value));
    }
  }

  append(node, children);
  return node;
}

export function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    parent.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return parent;
}

export function clear(node) {
  node.replaceChildren();
  return node;
}

export const frag = (...children) => append(document.createDocumentFragment(), children);
