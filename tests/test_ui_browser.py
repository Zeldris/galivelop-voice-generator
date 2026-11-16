"""F5.7: the web interface run for real in a headless Chrome over the DevTools protocol (tests/browser.py). The API
does not exist yet (F4), so the server is the static one of ``gvoice/server.py`` (in a thread, free port) and the page
opens with ``?mock=1`` (the in-browser simulator, ``gvoice/ui/mock/api-mock.js``). Every scenario ends by asserting the
page reported no exception, no console error, no CSP violation and no failed load. Skipped when no Chrome is found
(see ``GVOICE_TEST_CHROME``)."""
import json
import shutil
import unittest
from pathlib import Path

from gvoice import server
from tests import browser

PROJECT = "example-world"
ORDER = "narrator"


@unittest.skipUnless(browser.find_chrome(), "no Chrome/Chromium found (set GVOICE_TEST_CHROME)")
class UiBase(unittest.TestCase):
    """One server and one browser for the whole class; each test opens a fresh tab."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(browser.scratch_dir("gvoice-ui-")).resolve()  # never in /tmp (a small tmpfs)
        try:
            cls.srv = server.make_server(0)
            cls.port = cls.srv.port
            server.start_thread(cls.srv)
            cls.browser = browser.Browser()
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "browser", None):
            cls.browser.close()
        if getattr(cls, "srv", None):
            cls.srv.shutdown()
            cls.srv.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.page = self.browser.new_page()
        self.browser.take_problems()
        self.addCleanup(self.close_page)

    def close_page(self):
        self.shut(self.page)

    def shut(self, page):
        """Closes the tab itself (Chromium keeps it alive when only its socket closes), then the socket."""
        page.close()
        if page in self.browser.pages:
            self.browser.pages.remove(page)

    def replace_page(self, width, height):
        self.shut(self.page)
        self.page = self.browser.new_page(width=width, height=height)

    # helpers ---------------------------------------------------------------------------------------------------
    def open(self, route="/", wait="document.querySelector('#main h1')"):
        """Opens ``route`` (a hash route) on the simulator and waits for ``wait``."""
        self.page.goto("http://127.0.0.1:%d/ui/index.html?mock=1#%s" % (self.port, route))
        self.page.wait(wait)

    def js(self, expression):
        return self.page.evaluate(expression)

    def choose(self, select_id, value):
        self.js("(() => { const s = document.getElementById(%s); s.value = %s; s.dispatchEvent(new Event('change')); })()"
                % (json.dumps(select_id), json.dumps(value)))

    def click(self, selector):
        self.page.wait("document.querySelector(%s)" % json.dumps(selector))
        self.js("document.querySelector(%s).click()" % json.dumps(selector))

    def no_problems(self):
        self.page.pump(0.3)
        self.assertEqual(self.browser.take_problems(), [])


class Browse(UiBase):
    """Language and theme."""

    def texts(self):
        return self.js("[...document.querySelectorAll('[data-i18n]')].map(e => e.textContent.trim())")

    def test_language_switches_texts_and_the_html_lang(self):
        self.open("/", "document.querySelector('.project-card')")
        self.assertEqual(self.js("document.documentElement.lang"), "es")
        es = self.texts()
        self.assertIn("Saltar al contenido", es)
        self.choose("lang", "en")
        self.page.wait("document.documentElement.lang === 'en'")
        en = self.texts()
        self.assertEqual(len(en), len(es))
        self.assertNotEqual(en, es)
        self.assertNotIn("Saltar al contenido", en)
        self.choose("lang", "es")
        self.page.wait("document.documentElement.lang === 'es'")
        self.assertEqual(self.texts(), es)
        self.js("localStorage.clear()")
        self.no_problems()

    def test_theme_sets_the_attribute_and_the_background(self):
        self.open("/", "document.querySelector('.project-card')")
        background = lambda: self.js("getComputedStyle(document.body).backgroundColor")
        attribute = lambda: self.js("document.documentElement.dataset.theme || null")
        self.choose("theme", "light")
        self.assertEqual(attribute(), "light")
        light = background()
        self.choose("theme", "dark")
        self.assertEqual(attribute(), "dark")
        dark = background()
        self.assertNotEqual(light, dark)
        self.choose("theme", "auto")
        self.assertIsNone(attribute())   # auto: no attribute, the CSS follows prefers-color-scheme
        # the emulated media decides what auto looks like
        for scheme, expected in (("dark", dark), ("light", light)):
            self.page.call("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": scheme}]})
            self.assertEqual(background(), expected, "auto does not follow prefers-color-scheme: %s" % scheme)
        self.js("localStorage.clear()")
        self.no_problems()


class Screens(UiBase):
    # Sondeo de maquetación (as in gimg): the page does not scroll sideways, nothing visible leaves the window and no
    # element in flow overlaps its next sibling. Returns the list of readable problems.
    FIT_PROBE = r"""(() => {
      const W = innerWidth, out = [];
      const name = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + [...e.classList].map(c => '.' + c).join('');
      const shown = e => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
        return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && !e.closest('.sr-only'); };
      if (document.documentElement.scrollWidth > W + 1) out.push('página ' + document.documentElement.scrollWidth + ' px de ancho');
      const clipped = e => { for (let a = e.parentElement; a; a = a.parentElement) {
        const o = getComputedStyle(a).overflowX; if (o !== 'visible') return true; } return false; };
      const side = (e, n) => !n || ['absolute', 'fixed'].includes(getComputedStyle(n).position) ||
        ['absolute', 'fixed'].includes(getComputedStyle(e).position);
      const overlap = (r, q) => Math.min(r.right, q.right) - Math.max(r.left, q.left) > 2 &&
        Math.min(r.bottom, q.bottom) - Math.max(r.top, q.top) > 2;
      for (const e of document.querySelectorAll('body *')) {   // una sola pasada por el DOM
        if (!shown(e) || (e.closest('svg') && e.tagName.toLowerCase() !== 'svg')) continue;   // the parts of an icon touch by design
        const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
        if ((r.right > W + 1 || r.left < -1) && !clipped(e)) out.push(name(e) + ' sale del ancho (' + Math.round(r.left) + '..' + Math.round(r.right) + ')');
        const n = e.nextElementSibling;
        if (n && shown(n) && cs.display !== 'contents' && !side(e, n) && overlap(r, n.getBoundingClientRect()))
          out.push(name(e) + ' pisa a ' + name(n));
        const p = e.parentElement, pn = p && p.nextElementSibling;
        if (pn && shown(pn) && getComputedStyle(p).overflowY === 'visible' && !side(e, pn) && overlap(r, pn.getBoundingClientRect()))
          out.push(name(e) + ' se sale de ' + name(p) + ' y pisa a ' + name(pn));
        if (e.clientHeight > 2 && (cs.overflowY === 'hidden' || cs.overflowY === 'clip') && e.scrollHeight > e.clientHeight + 2)
          out.push(name(e) + ' corta su contenido (' + e.scrollHeight + ' > ' + e.clientHeight + ')');
        if (['auto', 'scroll'].includes(cs.overflowX) && e.scrollWidth > e.clientWidth + 1 && !e.matches('.tabs'))
          out.push(name(e) + ' se desplaza a lo ancho (' + e.scrollWidth + ' > ' + e.clientWidth + ')');
      }
      return [...new Set(out)].slice(0, 12);
    })()"""

    def test_the_fit_probe_sees_what_sticks_out_of_an_auto_overflow_box(self):
        # (el hijo se estiliza por CSSOM: la CSP no deja `style=""` en el HTML)
        self.open("/", "document.querySelector('.project-card')")
        self.assertEqual(self.js(self.FIT_PROBE), [])
        self.js("""(() => { const d = document.createElement('div'); d.id = 'probe-box'; d.style.cssText = 'overflow:auto;width:100px';
            const c = document.createElement('div'); c.style.cssText = 'width:300px;height:10px';
            d.append(c); document.body.append(d); return true; })()""")
        self.assertEqual([p for p in self.js(self.FIT_PROBE) if "probe-box" in p], ["div#probe-box se desplaza a lo ancho (300 > 100)"])

    def test_the_fit_probe_sees_what_leaves_the_window(self):
        self.replace_page(360, 800)
        self.open("/", "document.querySelector('.project-card')")
        self.js("""(() => { const d = document.createElement('div'); d.id = 'wide'; d.style.cssText = 'width:600px;height:10px';
            document.body.append(d); return true; })()""")
        found = self.js(self.FIT_PROBE)
        self.assertTrue(any("página" in p for p in found), found)
        self.assertTrue(any(p.startswith("div#wide sale del ancho") for p in found), found)

    def test_main_screens_fit_at_360_768_and_1280(self):
        order = "%s/o/%s" % (PROJECT, ORDER)
        screens = [
            ("proyectos", "/", "document.querySelector('.project-card')"),
            ("proyecto", "/p/%s" % PROJECT, "document.querySelector('#main h1') && document.querySelector('a.card')"),
            ("pedido con tomas", "/p/%s" % order, "document.querySelector('#main h1') && document.querySelectorAll('.take-card').length >= 2"),
            ("comparación A/B", "/p/%s/ab?a=2&b=3" % order, "document.querySelector('#main h1') && document.querySelector('.compare-transport')"),
        ]
        for width in (360, 768, 1280):
            self.replace_page(width, 800)
            for label, route, ready in screens:
                with self.subTest(width=width, screen=label):
                    try:
                        self.open(route, ready)
                        self.page.pump(0.3)
                        self.assertEqual(self.js(self.FIT_PROBE), [])
                    finally:   # un diálogo modal abierto inutilizaría las pantallas siguientes
                        self.js("document.querySelectorAll('dialog[open]').forEach(d => d.close())")
        self.no_problems()


class QueueDrawer(UiBase):
    """The queue pill and its drawer on the simulator's queue (1 running, 1 queued, 1 failed)."""

    def entry(self, n):
        return "#queue-drawer .queue-entry[data-entry='%d']" % n

    def test_pill_drawer_cancel_and_clear(self):
        self.open("/", "document.querySelector('.queue-pill')")
        self.page.wait("document.querySelector('.queue-pill').textContent.includes('1 en cola')")
        self.click(".queue-pill")
        self.page.wait("!document.getElementById('queue-drawer').hidden")
        self.page.wait("document.querySelectorAll('#queue-drawer .queue-entry').length === 3")
        # la fallida dice por qué, con ✗ y texto (nunca solo color)
        failed = self.js("document.querySelector(%s).textContent" % json.dumps(self.entry(0)))
        self.assertIn("✗", failed)
        self.assertIn("out of memory", failed)
        # cancelar la confirmación no toca nada
        self.click("[data-fid=clear-all]")
        self.page.wait("document.querySelector('dialog.confirm[open]')")
        self.click("dialog.confirm button:not(.btn-danger)")
        self.page.wait("!document.querySelector('dialog.confirm[open]')")
        self.assertTrue(self.js("document.querySelector(%s).classList.contains('is-queued')" % json.dumps(self.entry(2))))
        # confirmarla cancela lo que espera
        self.click("[data-fid=clear-all]")
        self.page.wait("document.querySelector('dialog.confirm[open]')")
        self.click("dialog.confirm button.btn-danger")
        self.page.wait("document.querySelector(%s + '.is-cancelled')" % json.dumps(self.entry(2)))
        self.page.wait("!document.querySelector('.queue-pill').textContent.includes('en cola')")
        # Esc cierra el cajón
        self.page.key("Escape")
        self.page.wait("document.getElementById('queue-drawer').hidden")
        self.no_problems()

    def test_cancel_one_entry(self):
        self.open("/", "document.querySelector('.queue-pill')")
        self.click(".queue-pill")
        self.click("[data-fid=cancel-2]")
        self.page.wait("document.querySelector(%s + '.is-cancelled')" % json.dumps(self.entry(2)))
        self.no_problems()

    def test_the_open_drawer_fits_at_360_768_and_1280(self):
        for width in (360, 768, 1280):
            with self.subTest(width=width):
                self.replace_page(width, 800)
                self.open("/", "document.querySelector('.queue-pill')")
                self.click(".queue-pill")
                self.page.wait("document.querySelectorAll('#queue-drawer .queue-entry').length === 3")
                self.page.pump(0.3)
                self.assertEqual(self.js(Screens.FIT_PROBE), [])
        self.no_problems()


if __name__ == "__main__":
    unittest.main()
