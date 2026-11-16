/* Nuevo en gvoice (no copiado de gimg) (F5.3). Comprobación en vivo de la ficha (F5.3), lógica pura sin DOM: espera a que se deje de escribir y descarta las
   respuestas viejas. Cada `request` invalida lo anterior (el temporizador pendiente y la petición en vuelo), así que solo
   llega a `onResult`/`onError` la respuesta de la última ficha pedida. `setTimer`/`clearTimer` se pueden sustituir (tests). */

import { latest, STALE } from './async-guard.js';

export const CHECK_DELAY_MS = 300;

export function createSheetChecker({ check, onResult, onError = () => {}, delay = CHECK_DELAY_MS, setTimer = setTimeout, clearTimer = clearTimeout }) {
  const guard = latest();
  let timer = null;
  let last = null; // JSON de la última ficha pedida: la misma ficha no se vuelve a mandar
  const drop = () => { if (timer !== null) { clearTimer(timer); timer = null; } };
  return {
    request(sheet) {
      const json = JSON.stringify(sheet);
      if (json === last) return;
      last = json;
      drop();
      guard.invalidate(); // lo que esté en vuelo de la ficha anterior ya no vale
      timer = setTimer(async () => {
        timer = null;
        try {
          const res = await guard.run(check(sheet));
          if (res !== STALE) onResult(res);
        } catch (e) {
          last = null; // tras un fallo se puede reintentar con la misma ficha
          onError(e);
        }
      }, delay);
    },
    /** Descarta lo pendiente y lo que esté en vuelo (al cerrar el panel). */
    cancel() { guard.invalidate(); last = null; drop(); },
  };
}
