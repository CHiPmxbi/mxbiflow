from mxbi.utils.logger import logger


class MockPump:
    def give_reward(self, duration: int) -> None:
        logger.info(f"Mock reward for {duration} ms")

    def stop_reward(self, all: bool) -> None:
        logger.info(f"Mock stop reward (all={all})")

    def reverse(self) -> None:
        logger.info("Mock reverse")
