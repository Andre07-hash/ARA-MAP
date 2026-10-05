/* Human labels for the validation codes, used by the import preview chips. */

export const ETIQUETAS = {
  SIN_COORDENADAS:          "Sin coordenadas",
  COORD_FUERA_MEXICO:       "Coordenadas fuera de México",
  COORD_INVERTIDA:          "X y Y invertidas",
  PRECIO_INCONSISTENTE:     "Precio inconsistente",
  PRECIO_CERO:              "Precio en cero",
  SUPERFICIE_INCONSISTENTE: "Superficie inconsistente",
  VALOR_NO_NUMERICO:        "Valor no numérico",
  CAMPO_FALTANTE:           "Campo faltante",
  AFECTACION_ALTA:          "Afectación alta",
  AFECTACION_FORMATO:       "Formato de afectación",
  DUPLICADO_EN_BASE:        "Posible duplicado",
};

const ERRORES = new Set([
  "COORD_FUERA_MEXICO", "COORD_INVERTIDA",
  "PRECIO_INCONSISTENTE", "SUPERFICIE_INCONSISTENTE",
]);

export const etiqueta = (codigo) => ETIQUETAS[codigo] ?? codigo;
export const esError = (codigo) => ERRORES.has(codigo);
