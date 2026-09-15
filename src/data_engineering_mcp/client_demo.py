import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run_demo() -> None:
    server = StdioServerParameters(command=sys.executable, args=["-m", "data_engineering_mcp.server"], env=None)
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resources()
            prompts = await session.list_prompts()
            print("Available tools:")
            print("\n".join(f"- {tool.name}" for tool in tools.tools))
            print("\nResources:")
            print("\n".join(f"- {resource.uri}" for resource in resources.resources))
            print("\nPrompts:")
            print("\n".join(f"- {prompt.name}" for prompt in prompts.prompts))
            calls = [
                ("get_job_status", {"job_name": "Customer_Load"}),
                ("get_database_schema", {"table_name": "orders"}),
                ("search_incidents", {"query": "database timeout", "limit": 3}),
            ]
            for name, arguments in calls:
                result = await session.call_tool(name, arguments)
                print(f"\n{name}:\n{json.dumps([getattr(item, 'text', str(item)) for item in result.content], indent=2)}")


def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()