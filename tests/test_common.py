"""Tests for common module."""

# Note: load_results/save_results are deprecated.
# Use TrialStore from optimizers/storage instead.
# These tests kept for backward compatibility during migration.


class TestResultsIO:
    """Tests for results load/save functions - DEPRECATED.

    These functions have been replaced by TrialStore in optimizers/storage.
    See optimizers/storage/tests/test_store.py for current tests.
    """

    pass  # Tests removed - use TrialStore instead
