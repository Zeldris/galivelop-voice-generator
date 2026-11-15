/* Nuevo en gvoice (no copiado de gimg) (F5.3). Comprobación en vivo de la ficha (F5.3), lógica pura sin DOM: espera a que se deje de escribir y descarta las
   respuestas viejas. Cada `request` invalida lo anterior (el temporizador pendiente y la petición en vuelo), así que solo
   llega a `onResult`/`onError` la respuesta de la última ficha pedida. `setTimer`/`clearTimer` se pueden sustituir (tests). */

export const CHECK_DELAY_MS = 300;

export function createSheetChecker({ check, onResult, onError = () => {}, delay = CHECK_DELAY_MS, setTimer = setTimeout, clearTimer = clearTimeout }) {
  let seq = 0;
  let timer = null;
  let last = null; // JSON de la última ficha pedida: la misma ficha no se vuelve a mandar
  const drop = () => { if (timer !== null) { clearTimer(timer); timer = null; } };
  return {
    request(sheet) {
      const json = JSON.stringify(sheet);
      if (json === last) return;
      last = json;
      drop();
      const mine = ++seq;
      timer = setTimer(async () => {
        timer = null;
        try {
          const res = await check(sheet);
          if (mine === seq) onResult(res);
        } catch (e) {
          if (mine === seq) { last = null; onError(e); } // tras un fallo se puede reintentar con la misma ficha
        }
      }, delay);
    },
    /** Descarta lo pendiente y lo que esté en vuelo (al cerrar el panel). */
    cancel() { seq++; last = null; drop(); },
  };
}
