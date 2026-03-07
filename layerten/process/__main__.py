import argparse
import logging
import sys

from layerten.process.orchestrator import run_processing


def main():
    parser = argparse.ArgumentParser(
        description="Process timeline events into Neo4j knowledge graph"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N events",
    )
    parser.add_argument(
        "--skip-agentic",
        action="store_true",
        help="Skip agentic (LLM) extraction, deterministic only",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe graph and checkpoint before processing",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    run_processing(
        limit=args.limit,
        skip_agentic=args.skip_agentic,
        reset=args.reset,
    )


if __name__ == "__main__":
    main()
