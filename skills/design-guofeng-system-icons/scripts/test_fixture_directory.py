"""Test-only workspace fixtures using inherited ACLs, never permission changes."""
import os
from pathlib import Path
import shutil
import uuid


class WorkspaceTemporaryDirectory:
    def __init__(self, prefix="xgf-"):
        self.base = Path(os.environ.get("XGF_TEST_ROOT", Path.cwd() / ".test-fixtures")).resolve()
        self.base.mkdir(parents=True, exist_ok=True)
        self.path = self.base / ("xgf-" + prefix + uuid.uuid4().hex)
        self.path.mkdir()
        self.name = str(self.path)

    def cleanup(self):
        # Verify the resolved target is our single owned child before recursive cleanup.
        target = self.path.resolve()
        if target.parent != self.base or not target.name.startswith("xgf-") or self.path.is_symlink():
            raise ValueError("Refusing cleanup outside owned fixture directory")
        if target.exists():
            shutil.rmtree(target)
