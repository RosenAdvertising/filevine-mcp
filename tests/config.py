from pathlib import Path

from mcp_test_kit.config import ResilienceConfig, SpecCheckConfig, ToolkitConfig
from filevine_mcp.server import mcp

_TESTS_DIR = Path(__file__).parent

TOOLKIT = ToolkitConfig(
    mcp_server=mcp,
    spec_check=SpecCheckConfig(
        endpoints_path=_TESTS_DIR.parent / "endpoints.yaml",
        openapi_path=_TESTS_DIR.parent
        / "endpoints.yaml",  # dummy — contract tier skipped
    ),
    source_path=_TESTS_DIR.parent / "filevine_mcp",
    module_path="filevine_mcp",
    server_path=_TESTS_DIR.parent / "filevine_mcp" / "server.py",
    resilience=ResilienceConfig(tools_to_timeout_test=["get_current_user"]),
    skip_tiers={
        "contract": "Filevine OpenAPI specs are US/CA/CJIS variants — contract tier not yet configured",
        "smoke": "requires live sandbox credentials",
    },
)
