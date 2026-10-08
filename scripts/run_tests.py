"""Run the offline suite and reject empty discovery instead of reporting success."""

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def main():
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    count = suite.countTestCases()
    if count == 0:
        print("No tests discovered. Restore the tests before accepting this check.", file=sys.stderr)
        return 1
    print(f"Discovered {count} offline tests.", flush=True)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() and result.testsRun == count else 1


if __name__ == "__main__":
    sys.exit(main())
