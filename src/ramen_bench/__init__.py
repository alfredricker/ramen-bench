def main() -> None:
    """The ``ramen-bench`` command (``ramen_bench.run``)."""
    import sys

    from .run import main as run_main

    sys.exit(run_main())
