/* Copiado de gimg@46248251 (D7); escrito de nuevo para gvoice (F5.3). Comprobación en vivo de la ficha (F5.3), lógica pura sin DOM: espera a que se deje de escribir y descarta las
   respuestas viejas. Cada `request` invalida lo anterior (el temporizador pendiente y la petición en vuelo), así que solo
   llega a `onResult`/`onError` la respuesta de la última ficha pedida. `setTimer`/`clearTimer` se pueden sustituir (tests). */

export const CHECK_DELAY_MS = 300;

export function createSheetChecker({ check, onResult, onError = () => {}, delay = CHECK_DELAY_MS, setTimer = setTimeout, clearTimer = clearTimeout }) {
  let seq = 0;
  let timer = null;
  const drop = () => { if (timer !== null) { clearTimer(timer); timer = null; } };
  return {
    request(sheet) {
      drop();
      const mine = ++seq;
      timer = setTimer(async () => {
        timer = null;
        try {
          const res = await check(sheet);
          if (mine === seq) onResult(res);
        } catch (e) {
          if (mine === seq) onError(e);
        }
      }, delay);
    },
    /** Descarta lo pendiente y lo que esté en vuelo (al cerrar el panel). */
    cancel() { seq++; drop(); },
  };
}
