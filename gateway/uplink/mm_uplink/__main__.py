"""mm-uplink [--config /etc/medmusketeer/uplink.toml]: runs the uplink until SIGTERM."""
import argparse
import logging
import signal
from pathlib import Path

from mm_uplink.config import Config
from mm_uplink.service import Uplink


def main() -> None:
    parser = argparse.ArgumentParser(prog="mm-uplink", description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("/etc/medmusketeer/uplink.toml"))
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uplink = Uplink(Config.load(args.config))
    signal.signal(signal.SIGTERM, lambda *_: uplink.stop())
    uplink.run_forever()


if __name__ == "__main__":
    main()
