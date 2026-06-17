from app.core.ui_task_dispatch import (
    distribute_suite_indices_by_weight,
    max_device_concurrency,
    normalize_device_assignments,
)


def test_normalize_device_assignments_with_concurrency():
    rows = normalize_device_assignments(
        None,
        [{"device_id": "dev1", "weight": 2, "concurrency": 5}],
    )
    assert rows == [("dev1", 2, 5)]


def test_normalize_serial_device_uses_default_concurrency():
    rows = normalize_device_assignments("dev-a", None, default_concurrency=4)
    assert rows == [("dev-a", 1, 4)]


def test_max_device_concurrency():
    rows = [("a", 1, 2), ("b", 1, 5)]
    assert max_device_concurrency(rows) == 5


def test_single_device_gets_all_suite_indices():
    indices = distribute_suite_indices_by_weight([1, 2, 3, 1], [("dev", 1)])
    assert indices == [0, 0, 0, 0]
