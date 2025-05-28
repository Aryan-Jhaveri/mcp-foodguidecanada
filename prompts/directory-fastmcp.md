Directory structure:
└── jlowin-fastmcp/
    ├── README.md
    ├── AGENTS.md
    ├── justfile
    ├── LICENSE
    ├── pyproject.toml
    ├── uv.lock
    ├── Windows_Notes.md
    ├── .pre-commit-config.yaml
    ├── .python-version
    ├── docs/
    │   ├── docs.json
    │   ├── style.css
    │   ├── assets/
    │   ├── clients/
    │   │   ├── advanced-features.mdx
    │   │   ├── client.mdx
    │   │   └── transports.mdx
    │   ├── deployment/
    │   │   ├── asgi.mdx
    │   │   ├── authentication.mdx
    │   │   ├── cli.mdx
    │   │   └── running-server.mdx
    │   ├── getting-started/
    │   │   ├── installation.mdx
    │   │   ├── quickstart.mdx
    │   │   └── welcome.mdx
    │   ├── patterns/
    │   │   ├── contrib.mdx
    │   │   ├── decorating-methods.mdx
    │   │   ├── fastapi.mdx
    │   │   ├── http-requests.mdx
    │   │   └── testing.mdx
    │   ├── servers/
    │   │   ├── composition.mdx
    │   │   ├── context.mdx
    │   │   ├── fastmcp.mdx
    │   │   ├── openapi.mdx
    │   │   ├── prompts.mdx
    │   │   ├── proxy.mdx
    │   │   ├── resources.mdx
    │   │   └── tools.mdx
    │   └── snippets/
    │       └── version-badge.mdx
    ├── examples/
    │   ├── complex_inputs.py
    │   ├── desktop.py
    │   ├── echo.py
    │   ├── in_memory_proxy_example.py
    │   ├── memory.py
    │   ├── mount_example.py
    │   ├── sampling.py
    │   ├── screenshot.py
    │   ├── serializer.py
    │   ├── simple_echo.py
    │   ├── tags_example.py
    │   ├── text_me.py
    │   └── smart_home/
    │       ├── README.md
    │       ├── pyproject.toml
    │       ├── uv.lock
    │       └── src/
    │           └── smart_home/
    │               ├── __init__.py
    │               ├── __main__.py
    │               ├── hub.py
    │               ├── py.typed
    │               ├── settings.py
    │               └── lights/
    │                   ├── __init__.py
    │                   ├── hue_utils.py
    │                   └── server.py
    ├── src/
    │   └── fastmcp/
    │       ├── __init__.py
    │       ├── exceptions.py
    │       ├── py.typed
    │       ├── settings.py
    │       ├── cli/
    │       │   ├── __init__.py
    │       │   ├── claude.py
    │       │   ├── cli.py
    │       │   └── run.py
    │       ├── client/
    │       │   ├── __init__.py
    │       │   ├── base.py
    │       │   ├── client.py
    │       │   ├── logging.py
    │       │   ├── progress.py
    │       │   ├── roots.py
    │       │   ├── sampling.py
    │       │   └── transports.py
    │       ├── contrib/
    │       │   ├── README.md
    │       │   ├── bulk_tool_caller/
    │       │   │   ├── README.md
    │       │   │   ├── __init__.py
    │       │   │   ├── bulk_tool_caller.py
    │       │   │   └── example.py
    │       │   └── mcp_mixin/
    │       │       ├── README.md
    │       │       ├── __init__.py
    │       │       ├── example.py
    │       │       └── mcp_mixin.py
    │       ├── low_level/
    │       │   ├── README.md
    │       │   └── __init__.py
    │       ├── prompts/
    │       │   ├── __init__.py
    │       │   ├── prompt.py
    │       │   └── prompt_manager.py
    │       ├── resources/
    │       │   ├── __init__.py
    │       │   ├── resource.py
    │       │   ├── resource_manager.py
    │       │   ├── template.py
    │       │   └── types.py
    │       ├── server/
    │       │   ├── __init__.py
    │       │   ├── context.py
    │       │   ├── dependencies.py
    │       │   ├── http.py
    │       │   ├── openapi.py
    │       │   ├── proxy.py
    │       │   └── server.py
    │       ├── tools/
    │       │   ├── __init__.py
    │       │   ├── tool.py
    │       │   └── tool_manager.py
    │       └── utilities/
    │           ├── __init__.py
    │           ├── cache.py
    │           ├── decorators.py
    │           ├── exceptions.py
    │           ├── json_schema.py
    │           ├── logging.py
    │           ├── mcp_config.py
    │           ├── openapi.py
    │           ├── tests.py
    │           └── types.py
    ├── tests/
    │   ├── __init__.py
    │   ├── conftest.py
    │   ├── test_examples.py
    │   ├── cli/
    │   │   ├── test_cli.py
    │   │   └── test_run.py
    │   ├── client/
    │   │   ├── __init__.py
    │   │   ├── test_client.py
    │   │   ├── test_logs.py
    │   │   ├── test_openapi.py
    │   │   ├── test_progress.py
    │   │   ├── test_roots.py
    │   │   ├── test_sampling.py
    │   │   ├── test_sse.py
    │   │   └── test_streamable_http.py
    │   ├── contrib/
    │   │   ├── __init__.py
    │   │   ├── test_bulk_tool_caller.py
    │   │   └── test_mcp_mixin.py
    │   ├── deprecated/
    │   │   ├── __init__.py
    │   │   ├── test_deprecated.py
    │   │   ├── test_mount_separators.py
    │   │   ├── test_resource_prefixes.py
    │   │   └── test_route_type_ignore.py
    │   ├── prompts/
    │   │   ├── __init__.py
    │   │   ├── test_prompt.py
    │   │   └── test_prompt_manager.py
    │   ├── resources/
    │   │   ├── __init__.py
    │   │   ├── test_file_resources.py
    │   │   ├── test_function_resources.py
    │   │   ├── test_resource_manager.py
    │   │   ├── test_resource_template.py
    │   │   └── test_resources.py
    │   ├── server/
    │   │   ├── __init__.py
    │   │   ├── test_app_state.py
    │   │   ├── test_auth_integration.py
    │   │   ├── test_context.py
    │   │   ├── test_file_server.py
    │   │   ├── test_import_server.py
    │   │   ├── test_lifespan.py
    │   │   ├── test_logging.py
    │   │   ├── test_mount.py
    │   │   ├── test_proxy.py
    │   │   ├── test_resource_prefix_formats.py
    │   │   ├── test_run_server.py
    │   │   ├── test_server.py
    │   │   ├── test_server_interactions.py
    │   │   ├── test_tool_annotations.py
    │   │   ├── http/
    │   │   │   ├── test_custom_routes.py
    │   │   │   ├── test_http_dependencies.py
    │   │   │   └── test_http_middleware.py
    │   │   └── openapi/
    │   │       ├── test_openapi.py
    │   │       ├── test_openapi_path_parameters.py
    │   │       └── test_route_map_fn.py
    │   ├── test_servers/
    │   │   ├── fastmcp_server.py
    │   │   ├── sse.py
    │   │   └── stdio.py
    │   ├── tools/
    │   │   ├── __init__.py
    │   │   ├── test_tool.py
    │   │   └── test_tool_manager.py
    │   └── utilities/
    │       ├── __init__.py
    │       ├── test_cache.py
    │       ├── test_decorated_function.py
    │       ├── test_json_schema.py
    │       ├── test_logging.py
    │       ├── test_mcp_config.py
    │       ├── test_tests.py
    │       ├── test_typeadapter.py
    │       ├── test_types.py
    │       └── openapi/
    │           ├── __init__.py
    │           ├── conftest.py
    │           ├── test_openapi.py
    │           ├── test_openapi_advanced.py
    │           └── test_openapi_fastapi.py
    ├── .cursor/
    │   └── rules/
    │       └── core-mcp-objects.mdc
    └── .github/
        ├── labeler.yml
        ├── release.yml
        ├── ISSUE_TEMPLATE/
        │   ├── bug.yml
        │   ├── config.yml
        │   └── enhancement.yml
        └── workflows/
            ├── labeler.yml
            ├── publish.yml
            ├── run-static.yml
            └── run-tests.yml
