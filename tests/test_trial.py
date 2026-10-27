import unittest

from test_trial_status import Result

from mxbiflow.models.trial import schema_hint


class SchemaHintTests(unittest.TestCase):
    def test_hint_from_the_event_and_record_models(self) -> None:
        hint = schema_hint(Result)

        self.assertEqual(hint["version"], 1)
        self.assertEqual(
            hint["columns"],
            [
                "trial_id",
                "animal",
                "stage",
                "level",
                "correct",
                "record.response_latency_ms",
            ],
        )
        self.assertEqual(hint["fields"]["trial_id"], {"title": "Trial"})
        self.assertEqual(
            hint["fields"]["record.response_latency_ms"],
            {"title": "Reaction time", "unit": "ms"},
        )
        self.assertEqual(
            hint["fields"]["record.stimulus.frequency_hz"],
            {"title": "Frequency", "unit": "Hz"},
        )
        self.assertNotIn("record.animal", hint["fields"])
        self.assertEqual(hint["expanded"], ["record"])
        self.assertEqual(hint["collapsed"], ["record.stimulus"])

    def test_hint_without_a_record_model(self) -> None:
        hint = schema_hint(None)

        self.assertEqual(hint["expanded"], [])
        self.assertNotIn("record.response_latency_ms", hint["columns"])


if __name__ == "__main__":
    unittest.main()
