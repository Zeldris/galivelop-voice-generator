/* Nuevo en gvoice (no copiado de gimg) (retro F5.3). Guardas para peticiones asíncronas de los componentes, sin DOM.
   Tres piezas: `latest()` (solo cuenta la última petición lanzada), `busy(fn)` (una llamada a la vez, con la bandera
   repuesta en `finally`) y `lifetime()` (la vida de una vista: nada se pinta ni avisa tras cambiar de ruta). */

/** Marca que devuelve `run` cuando la petición ya no es la última: su respuesta (o su fallo) se descarta. */
export const STALE = Symbol('stale');

/** `run(promesa)` devuelve el valor de la promesa solo si ninguna petición posterior (ni `invalidate()`) la ha
    superado; si no, devuelve `STALE`, y lo mismo si falla (el fallo de una petición vieja no le importa a nadie). Un
    fallo de la última sí se propaga. `invalidate()` descarta lo que esté en vuelo sin lanzar otra petición. */
export function latest() {
  let seq = 0;
  return {
    async run(promise) {
      const mine = ++seq;
      try {
        const value = await promise;
        return mine === seq ? value : STALE;
      } catch (e) {
        if (mine === seq) throw e;
        return STALE;
      }
    },
    invalidate() { seq++; },
  };
}

/** Envuelve una función asíncrona: mientras corre, otra llamada no hace nada (devuelve `undefined`). La bandera se
    repone con `finally`, aunque `fn` lance. `keep(resultado)` verdadero la deja puesta tras acabar (p. ej. un diálogo
    que sigue abierto) hasta que alguien llama a `release()`. `onChange(activa)` avisa de cada cambio de la bandera. */
export function busy(fn, { keep = null, onChange = null } = {}) {
  let active = false;
  const set = (v) => { if (active !== v) { active = v; if (onChange) onChange(v); } };
  const wrapped = async (...args) => {
    if (active) return undefined;
    set(true);
    let result;
    let held = false;
    try {
      result = await fn(...args);
      held = Boolean(keep && keep(result));
      return result;
    } finally {
      if (!held) set(false);
    }
  };
  wrapped.release = () => set(false);
  Object.defineProperty(wrapped, 'active', { get: () => active });
  return wrapped;
}

/** Vida de una vista: `alive()` hasta que se llama a `end()` (en su `cleanup`). */
export function lifetime() {
  let alive = true;
  return { alive: () => alive, end() { alive = false; } };
}
