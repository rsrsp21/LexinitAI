import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from redis import Redis
from rq import Queue, Worker

from backend.config import Config


def main():
    if not Config.REDIS_URL:
        raise RuntimeError("REDIS_URL is required to start the generation worker.")
    connection = Redis.from_url(Config.REDIS_URL)
    queue = Queue(Config.GENERATION_QUEUE_NAME, connection=connection)
    Worker([queue], connection=connection).work()


if __name__ == "__main__":
    main()
