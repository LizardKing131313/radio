import asyncio

from manager.hls import HLS
from manager.liquidsoap.liquidsoap import LiquidSoap
from manager.logger import configure_logging
from manager.runner.control import ControlBus, ControlNode
from manager.runner.node import Node
from manager.runner.runner import Runner


async def start_radio() -> None:
    run_id = configure_logging()

    control_bus = ControlBus()

    nodes = [
        Node(id=ControlNode.FFMPEG, runnable=HLS(node_id=ControlNode.FFMPEG)),
        Node(
            id=ControlNode.LIQUID_SOAP,
            runnable=LiquidSoap(node_id=ControlNode.LIQUID_SOAP),
            parent={ControlNode.FFMPEG},
        ),
    ]

    runner = Runner(run_id=run_id, control_bus=control_bus, nodes=nodes)

    await runner.execute()


def run() -> int:
    try:
        asyncio.run(start_radio())
        return 0
    except (KeyboardInterrupt, SystemExit):
        return 0


if __name__ == "__main__":
    raise SystemExit(run())
