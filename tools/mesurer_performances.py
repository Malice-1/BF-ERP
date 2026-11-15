"""Reproducible local measurements on an isolated, disposable SQLite database."""
import argparse
from collections import deque
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.test_settings"

import django

django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.test.runner import DiscoverRunner
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from budgeting.models import BudgetProduct, CostCenter, Funding
from purchasing.models import Allocation, AnnualEnvelope, EnvelopeVersion
from purchasing.services import create_purchase_request, add_purchase_request_line
from purchasing.models import DetailedProduct
from suppliers.models import Supplier


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    if connection.vendor != "sqlite" or settings.DATABASES["default"]["NAME"] != ":memory:":
        raise RuntimeError("This measurement requires the isolated in-memory test settings")
    runner = DiscoverRunner(verbosity=0, interactive=False)
    runner.setup_test_environment()
    databases = runner.setup_databases()
    connection.queries_log = deque(maxlen=100000)
    results = []
    try:
        admin = get_user_model().objects.create_superuser("perf_admin")
        supplier = Supplier.objects.create(code="PERF", name="Synthetic benchmark supplier")
        cdf = CostCenter.objects.create(code="PERF", label="Synthetic CDF")
        cdf.managers.add(admin)
        funding = Funding.objects.create(code="PERF", label="Synthetic funding")
        envelope = AnnualEnvelope.objects.create(year=timezone.localdate().year)
        version = EnvelopeVersion.objects.create(envelope=envelope, label="Synthetic benchmark")
        client = Client()
        client.force_login(admin)

        def measure(name, size, url, parameters=None):
            warmup = client.get(url, parameters or {})
            if warmup.status_code != 200:
                raise AssertionError((name, warmup.status_code))
            times, counts, sizes, peaks = [], [], [], []
            for _ in range(args.repetitions):
                connection.queries_log.clear()
                tracemalloc.start()
                started = time.perf_counter()
                with CaptureQueriesContext(connection) as captured:
                    response = client.get(url, parameters or {})
                elapsed = (time.perf_counter() - started) * 1000
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                if response.status_code != 200:
                    raise AssertionError((name, response.status_code))
                times.append(elapsed)
                counts.append(len(captured))
                sizes.append(len(response.content))
                peaks.append(peak)
            result = dict(scenario=name, volume=size, repetitions=args.repetitions,
                          median_ms=round(statistics.median(times), 2),
                          min_ms=round(min(times), 2), max_ms=round(max(times), 2),
                          sql_min=min(counts), sql_max=max(counts),
                          response_bytes=max(sizes), python_peak_bytes=max(peaks))
            results.append(result)
            print(json.dumps(result), flush=True)

        previous = 0
        for size in (10, 100, 1000):
            products = BudgetProduct.objects.bulk_create([
                BudgetProduct(code=f"PERF-{index:04d}", label=f"Synthetic product {index}")
                for index in range(previous, size)
            ])
            Allocation.objects.bulk_create([
                Allocation(version=version, cost_center=cdf, funding=funding,
                           budget_product=product, amount=1000000)
                for product in products
            ])
            measure("allocation_version_page", size,
                    reverse("purchasing:budget_version", args=[version.pk]))
            measure("budget_balances_page", size, reverse("purchasing:budgets"),
                    {"version": version.pk})
            previous = size
        product = BudgetProduct.objects.first()
        detailed = DetailedProduct.objects.create(code="PERF", label="Synthetic article", budget_product=product)
        purchase = create_purchase_request(actor=admin, supplier=supplier)
        previous = 0
        for size in (1, 10, 50):
            for index in range(previous, size):
                add_purchase_request_line(request_id=purchase.pk, actor=admin,
                    expected_revision=purchase.revision, detailed_product=detailed,
                    description=f"Synthetic line {index}", cost_center=cdf, funding=funding,
                    quantity=1, unit_price=10, vat_rate=21)
                purchase.refresh_from_db()
            measure("purchase_detail_page", size,
                    reverse("purchasing:detail", args=[purchase.pk]))
            previous = size
        payload = {
            "measured_at": timezone.now().isoformat(),
            "python": platform.python_version(), "django": django.get_version(),
            "platform": platform.platform(), "database": "SQLite in memory",
            "protocol": "Django test client, one warmup, tracemalloc and SQL capture enabled; no network or browser",
            "limitations": "No production throughput, PostgreSQL lock, disk I/O, concurrent user, browser or p95 measurement",
            "results": results,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        runner.teardown_databases(databases)
        runner.teardown_test_environment()


if __name__ == "__main__":
    main()
