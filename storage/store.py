"""Trial store for persisting benchmark results."""

import json
from pathlib import Path
from typing import Any

from .models import ServiceType, Trial


class TrialStore:
    """Store for benchmark trial results.

    Handles loading, saving, and querying trial data from a JSON file.
    Trial IDs are auto-incremented. Supports the flat JSON structure
    used by all optimizers.

    Example:
        store = TrialStore(Path("results.json"), service="redis")

        # Add a trial (dict from optimizer)
        store.add_dict({
            "trial": 1,
            "timestamp": "2026-02-09T12:00:00",
            "cloud": "selectel",
            "config": {"mode": "single", "cpu_per_node": 4, ...},
            "nodes": 1,
            "ops_per_sec": 150000,
            "p99_latency_ms": 1.2,
            ...
        })

        # Find trials
        results = store.find(cloud="selectel", successful_only=True)

        # Check if config exists
        cached = store.find_by_config_key(config_key)
    """

    def __init__(self, path: Path, service: ServiceType):
        """Initialize store with path to JSON file and service type.

        Args:
            path: Path to JSON file for persistence
            service: Service type for all trials in this store
        """
        self.path = path
        self.service = service
        self._trials: list[Trial] | None = None

    @property
    def trials(self) -> list[Trial]:
        """Lazy-load trials from disk."""
        if self._trials is None:
            self._trials = self._load()
        return self._trials

    def _load(self) -> list[Trial]:
        """Load trials from JSON file, filtering by service."""
        if not self.path.exists():
            return []

        with open(self.path) as f:
            data = json.load(f)

        trials = []
        for item in data:
            trial = self._parse_trial(item)
            # Only load trials for this service
            if trial and trial.service == self.service:
                trials.append(trial)
        return trials

    def _load_all(self) -> list[Trial]:
        """Load all trials from JSON file (all services)."""
        if not self.path.exists():
            return []

        with open(self.path) as f:
            data = json.load(f)

        trials = []
        for item in data:
            try:
                trials.append(Trial.model_validate(item))
            except Exception:
                pass
        return trials

    def _parse_trial(self, data: dict[str, Any]) -> Trial | None:
        """Parse a dict into a Trial."""
        try:
            # Add service if not present (legacy files)
            if "service" not in data:
                data["service"] = self.service

            return Trial.model_validate(data)
        except Exception:
            # Skip invalid entries
            return None

    def _save(self) -> None:
        """Save trials to JSON file, preserving other services' data."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Load all existing trials (all services)
        all_trials = self._load_all()

        # Remove old trials for this service, add current ones
        other_trials = [t for t in all_trials if t.service != self.service]
        combined = other_trials + self.trials

        # Serialize excluding None values and defaults (0.0) for cleaner JSON
        data = [
            t.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
            for t in combined
        ]

        with open(self.path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _next_id(self) -> int:
        """Get next available trial ID."""
        if not self.trials:
            return 1
        # Use max of both id and trial fields for compatibility
        max_id = max((t.id or 0) for t in self.trials)
        max_trial = max((t.trial or 0) for t in self.trials)
        return max(max_id, max_trial) + 1

    def add(self, trial: Trial) -> Trial:
        """Add a Trial object to the store.

        Auto-assigns an ID if not set.
        Saves to disk immediately.
        """
        if trial.id is None:
            trial.id = self._next_id()

        self.trials.append(trial)
        self._save()
        return trial

    def add_dict(self, data: dict[str, Any]) -> Trial:
        """Add a trial from a dict (as produced by optimizer save_result).

        This is the main entry point for optimizers. Automatically adds
        service field and assigns ID.

        Args:
            data: Trial data dict with metrics, config, etc.

        Returns:
            The created Trial object
        """
        # Ensure service is set
        data["service"] = self.service

        # Create trial
        trial = Trial.model_validate(data)

        # Auto-assign ID (always use _next_id for unique IDs)
        if trial.id is None:
            trial.id = self._next_id()

        self.trials.append(trial)
        self._save()
        return trial

    def find(
        self,
        *,
        cloud: str | None = None,
        successful_only: bool = False,
    ) -> list[Trial]:
        """Find trials matching criteria.

        Args:
            cloud: Filter by cloud provider
            successful_only: Only return trials without errors

        Returns:
            List of matching trials
        """
        results = self.trials

        if cloud:
            results = [t for t in results if t.cloud == cloud]

        if successful_only:
            results = [t for t in results if t.is_successful()]

        return results

    def find_by_config_key(self, config_key: str) -> Trial | None:
        """Find a successful trial matching the config key.

        Args:
            config_key: JSON string of config (from config_to_key())

        Returns:
            First successful matching trial, or None
        """
        import json as json_module

        target = json_module.loads(config_key)

        for trial in self.trials:
            if not trial.is_successful():
                continue
            if trial.get_config_key() == target:
                return trial

        return None

    def get_by_id(self, trial_id: int) -> Trial | None:
        """Get a trial by its ID."""
        for trial in self.trials:
            if trial.id == trial_id or trial.trial == trial_id:
                return trial
        return None

    def count(self) -> int:
        """Count total trials."""
        return len(self.trials)

    def clear(self) -> None:
        """Remove all trials and delete the file."""
        self._trials = []
        if self.path.exists():
            self.path.unlink()

    def reload(self) -> None:
        """Reload trials from disk, discarding in-memory changes."""
        self._trials = None

    def as_dicts(self) -> list[dict[str, Any]]:
        """Return all trials as dicts (for compatibility with existing code)."""
        return [t.model_dump(mode="json") for t in self.trials]
