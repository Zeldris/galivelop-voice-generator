import copy
import unittest

from gvoice import engine, orders, queue, schema, sheet, speech_locale
from tests.test_examples import ORDERS, read
from tests.test_worker import WorkerBase

ES_ES = ("Castilian Spanish from Spain, peninsular pronunciation with distinción (θ for z/ce/ci), "
         "not Latin American")


def errors(order):
    return [(e.path, e.code) for e in schema.validate(order, schema.load_schema("order"))]


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.voice = read("examples/order-voice-lectora-es.json")

    def test_example_declares_es_es(self):
        self.assertIn("examples/order-voice-lectora-es.json", ORDERS)
        self.assertEqual((self.voice["key"], self.voice["locale"]), ("lectora-es", "es-ES"))
        self.assertEqual(errors(self.voice), [])

    def test_every_locale_of_the_vocabulary_is_accepted(self):
        self.assertEqual(set(speech_locale.LOCALES), {"es-ES", "es-419", "en-US", "en-GB"})
        for locale in speech_locale.LOCALES:
            self.assertEqual(errors(dict(self.voice, locale=locale)), [], locale)

    def test_locale_outside_the_vocabulary_is_rejected(self):
        self.assertEqual(errors(dict(self.voice, locale="fr-FR")), [("/locale", "enum")])

    def test_line_cannot_have_locale(self):
        found = errors(dict(read("examples/order-line.json"), locale="es-ES"))
        self.assertTrue(any(path == "/locale" for path, _code in found), found)

    def test_voice_json_accepts_locale(self):
        voice = dict(read("examples/voice.json"), locale="es-ES")
        self.assertEqual(list(schema.validate(voice, schema.load_schema("voice"))), [])
        bad = dict(voice, locale="xx")
        self.assertEqual([e.path for e in schema.validate(bad, schema.load_schema("voice"))], ["/locale"])


class InstructionTests(unittest.TestCase):
    def test_phrase_is_the_fixed_one_and_last(self):
        self.assertEqual(speech_locale.phrase("es-ES"), ES_ES)
        self.assertEqual(sheet.instruction({"pitch": "low"}, "es-ES"), "Pitch: low. Locale: %s." % ES_ES)

    def test_without_locale_nothing_changes(self):
        self.assertEqual(sheet.instruction({"pitch": "low"}), "Pitch: low.")

    def test_languages(self):
        self.assertEqual([speech_locale.language(x) for x in (None, "es-ES", "es-419", "en-US", "en-GB")],
                         [None, "Spanish", "Spanish", "English", "English"])


class FlowTests(WorkerBase):
    def spy(self):
        seen = {"design": [], "line": []}

        class Spy(engine.FakeEngine):
            def design(self, job, should_cancel):
                seen["design"].append(job)
                return super().design(job, should_cancel)

            def line(self, job, should_cancel):
                seen["line"].append(job)
                return super().line(job, should_cancel)

        return Spy(), seen

    def lectora(self):
        order = copy.deepcopy(read("examples/order-voice-lectora-es.json"))
        order.pop("$schema")
        return order

    def test_locale_is_stored_and_resubmit_without_it_keeps_it(self):
        self.assertEqual(orders.submit(self.p, self.lectora())["locale"], "es-ES")
        self.assertEqual(orders.get(self.p, "lectora-es")["locale"], "es-ES")
        order = self.lectora()
        del order["locale"]
        orders.submit(self.p, order)  # the UI form has no locale field: it must not wipe the stored one
        self.assertEqual(orders.get(self.p, "lectora-es")["locale"], "es-ES")
        orders.submit(self.p, dict(order, locale="es-419"))
        self.assertEqual(orders.get(self.p, "lectora-es")["locale"], "es-419")

    def test_voice_take_has_the_phrase_and_the_language(self):
        orders.submit(self.p, self.lectora())
        spec, = orders.attempt_specs(self.p, "lectora-es", seed=101)
        self.assertTrue(spec["instruction"].endswith("Locale: %s." % ES_ES), spec["instruction"])
        queue.enqueue(self.p, "lectora-es", [spec])
        eng, seen = self.spy()
        self.run_worker(engine=eng)
        job, = seen["design"]
        self.assertEqual(job.language, "Spanish")
        self.assertIn(ES_ES, job.instruction)
        self.assertIn(ES_ES, orders.get(self.p, "lectora-es")["attempts"][0]["instruction"])

    def test_voice_without_locale_has_no_language_and_no_phrase(self):
        self.push("narrator", seed=7)
        eng, seen = self.spy()
        self.run_worker(engine=eng)
        job, = seen["design"]
        self.assertIsNone(job.language)
        self.assertNotIn("Locale:", job.instruction)

    def test_line_takes_the_language_of_its_voice(self):
        orders.submit(self.p, self.voice(key="narrator", locale="en-GB"))
        queue.enqueue(self.p, "narrator", orders.attempt_specs(self.p, "narrator", seed=7))
        self.run_worker()
        queue.choose(self.p, "narrator", 1)
        self.run_worker()
        orders.submit(self.p, self.line())
        queue.new_takes(self.p, "narrator/intro-01", seed=3)
        eng, seen = self.spy()
        self.run_worker(engine=eng)
        job, = seen["line"]
        self.assertEqual(job.language, "English")

    def test_line_takes_the_language_of_its_reference_take_not_the_voice_now(self):
        orders.submit(self.p, self.voice(key="narrator", locale="en-GB"))
        queue.enqueue(self.p, "narrator", orders.attempt_specs(self.p, "narrator", seed=7))
        self.run_worker()
        self.assertEqual(orders.get(self.p, "narrator")["attempts"][0]["locale"], "en-GB")
        queue.choose(self.p, "narrator", 1)
        self.run_worker()
        orders.submit(self.p, self.line())
        queue.new_takes(self.p, "narrator/intro-01", seed=3)
        orders.submit(self.p, self.voice(key="narrator", locale="es-ES"))  # changed before the worker runs
        eng, seen = self.spy()
        self.run_worker(engine=eng)
        job, = seen["line"]
        self.assertEqual(job.language, "English")
        self.assertEqual(orders.get(self.p, "narrator/intro-01")["attempts"][0]["locale"], "en-GB")

    def test_line_of_a_voice_without_locale_has_no_language(self):
        self.voice_done()
        orders.submit(self.p, self.line())
        queue.new_takes(self.p, "narrator/intro-01", seed=3)
        eng, seen = self.spy()
        self.run_worker(engine=eng)
        job, = seen["line"]
        self.assertIsNone(job.language)


if __name__ == "__main__":
    unittest.main()
