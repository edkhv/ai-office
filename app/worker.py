import signal
import time

from app.config import Settings
from app.db import engine_for, heartbeat
from app.knowledge import Knowledge
from app.providers import provider_for
from app.workflows import Workflows


def main():
    s = Settings()
    engine = engine_for(s)
    work = Workflows(engine, s, provider_for(s), Knowledge(engine, s))
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping:
        heartbeat(engine, time.time())
        if not work.process_one():
            time.sleep(0.5)


if __name__ == "__main__":
    main()
