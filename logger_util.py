import time
import logging

# Setup basic logging config
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LearnPilot")

class SystemMonitor:
    @staticmethod
    def log_request(mode, topic):
        logger.info(f"[REQUEST] Mode: {mode} | Topic: {topic}")

    @staticmethod
    def log_performance(start_time):
        duration = time.time() - start_time
        logger.info(f"[PERFORMANCE] Response generated in {duration:.2f} seconds")
