import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pygame import MOUSEBUTTONDOWN, QUIT, Event, Surface

from mxbiflow.scene.idle.idle import IDLE


class IDLEControlButtonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rewarder = Mock()
        mxbi = SimpleNamespace(
            screen_size=SimpleNamespace(width=200, height=100),
            rewarder=self.rewarder,
        )
        context = SimpleNamespace(mxbi=mxbi)
        loaded_image = Mock()
        loaded_image.convert_alpha.return_value = Surface((10, 10))

        with (
            patch("mxbiflow.scene.idle.idle.get_mxbiflow", return_value=context),
            patch("mxbiflow.scene.idle.idle.image.load", return_value=loaded_image),
        ):
            self.scene = IDLE()

        self.screen = Surface((200, 100))
        self.scene.draw(self.screen)

    @patch("mxbiflow.scene.idle.idle.event.post")
    def test_control_buttons_trigger_reward_and_quit(self, post: Mock) -> None:
        self.scene.handle_event(
            Event(MOUSEBUTTONDOWN, button=1, pos=(190, 10)),
        )
        self.scene.handle_event(
            Event(MOUSEBUTTONDOWN, button=1, pos=(190, 90)),
        )

        self.rewarder.give_reward.assert_called_once_with(1_000)
        posted_event = post.call_args.args[0]
        self.assertEqual(posted_event.type, QUIT)

    @patch("mxbiflow.scene.idle.idle.event.post")
    def test_other_clicks_do_not_trigger_controls(self, post: Mock) -> None:
        self.scene.handle_event(
            Event(MOUSEBUTTONDOWN, button=1, pos=(100, 50)),
        )
        self.scene.handle_event(
            Event(MOUSEBUTTONDOWN, button=3, pos=(190, 10)),
        )

        self.rewarder.give_reward.assert_not_called()
        post.assert_not_called()

    def test_draw_places_buttons_in_expected_corners(self) -> None:
        self.assertEqual(self.screen.get_at((190, 10)), (0, 160, 0, 255))
        self.assertEqual(self.screen.get_at((190, 90)), (200, 0, 0, 255))


if __name__ == "__main__":
    unittest.main()
