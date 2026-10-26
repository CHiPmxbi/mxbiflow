import unittest
from datetime import UTC, datetime
from unittest.mock import Mock, patch

from httpx import Response
from pymotego.errors import ProblemError
from test_session import make_session

from mxbiflow.infra.trial_status import BROADCAST_NAME, TrialPublisher, clear_trials


def make_publisher() -> tuple[TrialPublisher, Mock, Mock]:
    session = make_session()
    session.state.start_at = datetime(2026, 10, 26, 9, tzinfo=UTC)
    session.set_current_animal("animal-1")
    client = Mock()
    broadcast = Mock()
    return (
        TrialPublisher(session, client=client, broadcast=broadcast),
        client,
        broadcast,
    )


class TrialPublisherTests(unittest.TestCase):
    def test_patches_status_and_broadcasts_each_trial(self) -> None:
        publisher, client, broadcast = make_publisher()

        publisher.publish({"result": "correct"}, correct=True)
        publisher.publish({"result": "incorrect"}, correct=False)
        publisher.publish({"result": "aborted"}, correct=None)
        publisher.close()

        patches = [call.kwargs for call in client.patch_status.call_args_list]
        self.assertEqual(
            patches[0],
            {
                "state": "running",
                "subject": "animal-1",
                "task": "vocalization_discriminate@2",
                "started_at": datetime(2026, 10, 26, 9, tzinfo=UTC),
                "extra": {"trials": 1, "correct": 1, "accuracy": 1.0},
            },
        )
        self.assertEqual(
            patches[2]["extra"], {"trials": 3, "correct": 1, "accuracy": 0.5}
        )
        self.assertEqual(
            patches[3],
            {
                "state": "idle",
                "subject": None,
                "task": None,
                "started_at": None,
                "extra": None,
            },
        )

        name, event = broadcast.publish.call_args_list[0].args
        self.assertEqual(name, BROADCAST_NAME)
        self.assertEqual(event["animal"], "animal-1")
        self.assertEqual(event["stage"], "vocalization_discriminate")
        self.assertEqual(event["level"], 2)
        self.assertIs(event["correct"], True)
        self.assertEqual(event["record"], {"result": "correct"})
        client.close.assert_called_once_with()
        broadcast.close.assert_called_once_with()

    def test_accuracy_is_none_without_judged_trials(self) -> None:
        publisher, client, _ = make_publisher()

        publisher.publish({}, correct=None)
        publisher.close()

        extra = client.patch_status.call_args_list[0].kwargs["extra"]
        self.assertEqual(extra, {"trials": 1, "correct": 0, "accuracy": None})

    def test_record_is_made_json_compatible(self) -> None:
        publisher, _, broadcast = make_publisher()
        at = datetime(2026, 10, 26, tzinfo=UTC)

        publisher.publish({"at": at}, correct=True)
        publisher.close()

        _, event = broadcast.publish.call_args.args
        self.assertEqual(event["record"], {"at": str(at)})

    def test_failures_do_not_stop_publishing(self) -> None:
        publisher, client, broadcast = make_publisher()
        broadcast.publish.side_effect = [ConnectionError("down"), Mock()]

        with self.assertLogs("mxbiflow", level="INFO") as logs:
            publisher.publish({}, correct=True)
            publisher.publish({}, correct=True)
            publisher.close()

        self.assertEqual(broadcast.publish.call_count, 2)
        self.assertEqual(client.patch_status.call_count, 3)
        self.assertIn("failed to publish trial status", logs.output[0])
        self.assertIn("recovered", logs.output[1])


if __name__ == "__main__":
    unittest.main()


def problem(status: int) -> ProblemError:
    return ProblemError(
        Response(status), type="about:blank", title="error", detail=None
    )


class ClearTrialsTests(unittest.TestCase):
    def test_deletes_the_trials_broadcast(self) -> None:
        broadcast = Mock()

        clear_trials(broadcast)

        broadcast.delete.assert_called_once_with(BROADCAST_NAME)

    def test_missing_broadcast_or_cogmotego_is_ignored(self) -> None:
        for error in (problem(404), problem(500), ConnectionError("refused")):
            with self.subTest(error=error):
                clear_trials(Mock(delete=Mock(side_effect=error)))

    def test_closes_the_broadcast_it_creates(self) -> None:
        with patch("mxbiflow.infra.trial_status.Broadcast") as broadcast:
            clear_trials()

        broadcast.return_value.delete.assert_called_once_with(BROADCAST_NAME)
        broadcast.return_value.close.assert_called_once_with()
