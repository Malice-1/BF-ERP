"""Run the isolated Django suite and record real per-test results for QA docs."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.test_settings"

import django
django.setup()

from django.test.runner import DiscoverRunner

records = []


class RecordingResult(unittest.TextTestResult):
    def addSuccess(self, test):
        super().addSuccess(test)
        records.append({"test": test.id(), "status": "OK", "reason": ""})

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        records.append({"test": test.id(), "status": "Ignoré", "reason": reason})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        records.append({"test": test.id(), "status": "KO", "reason": self._exc_info_to_string(err, test)})

    def addError(self, test, err):
        super().addError(test, err)
        records.append({"test": test.id(), "status": "Erreur", "reason": self._exc_info_to_string(err, test)})

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            records.append({"test": subtest.id(), "status": "KO", "reason": self._exc_info_to_string(err, test)})


class RecordingRunner(DiscoverRunner):
    def get_resultclass(self):
        return RecordingResult


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    started = datetime.now(timezone.utc)
    failures = RecordingRunner(verbosity=1, interactive=False).run_tests([])
    summary = {"total": len(records), "passed": sum(x["status"] == "OK" for x in records),
               "skipped": sum(x["status"] == "Ignoré" for x in records),
               "failed": sum(x["status"] == "KO" for x in records),
               "errors": sum(x["status"] == "Erreur" for x in records)}
    payload = {"started_at": started.isoformat(), "finished_at": datetime.now(timezone.utc).isoformat(),
               "commit_base": commit, "working_tree": "Local documentary and unit-test changes included",
               "settings": "config.test_settings", "database": "SQLite in memory", "summary": summary, "tests": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
