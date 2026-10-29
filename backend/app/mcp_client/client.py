import os
import sys
import asyncio
from typing import Optional, List, Dict, Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import json

class MCPClient:
    def __init__(self, server_script: str):
        self.server_script = server_script
        self.session: Optional[ClientSession] = None
        self._portal: Optional[Any] = None
        self._portal_ctx = None
        self._session_ctx = None
        self._stdio_ctx = None

    async def connect(self):
        from anyio.from_thread import start_blocking_portal
        
        # Determine the Python executable
        python_exe = sys.executable
        
        server_params = StdioServerParameters(
            command=python_exe,
            args=[self.server_script],
            env=os.environ.copy()
        )
        
        self._portal_ctx = start_blocking_portal()
        self._portal = self._portal_ctx.__enter__()
        
        self._stdio_ctx = self._portal.wrap_async_context_manager(stdio_client(server_params))
        self.stdio, self.write = self._stdio_ctx.__enter__()
        
        self._session_ctx = self._portal.wrap_async_context_manager(ClientSession(self.stdio, self.write))
        self.session = self._session_ctx.__enter__()
        
        import time
        self._connected_time = time.time()
        import anyio
        await anyio.to_thread.run_sync(self._portal.call, self.session.initialize)

    def _is_stale(self) -> bool:
        if not hasattr(self, '_connected_time') or not self._connected_time:
            return False
        server_dir = os.path.dirname(self.server_script)
        try:
            for root, _, files in os.walk(server_dir):
                for f in files:
                    if f.endswith('.py'):
                        fpath = os.path.join(root, f)
                        if os.path.getmtime(fpath) > self._connected_time:
                            return True
        except Exception:
            pass
        return False

    async def _ensure_connected(self):
        if not self.session or self._is_stale():
            await self.close()
            await self.connect()

    async def get_tools(self) -> List[Any]:
        import anyio
        try:
            await self._ensure_connected()
            result = await anyio.to_thread.run_sync(self._portal.call, self.session.list_tools)
            return result.tools
        except Exception:
            self.session = None
            await self._ensure_connected()
            result = await anyio.to_thread.run_sync(self._portal.call, self.session.list_tools)
            return result.tools

    async def call_tool(self, name: str, arguments: dict) -> Any:
        import anyio
        try:
            await self._ensure_connected()
            result = await anyio.to_thread.run_sync(self._portal.call, self.session.call_tool, name, arguments)
            return result.content
        except Exception:
            self.session = None
            await self._ensure_connected()
            result = await anyio.to_thread.run_sync(self._portal.call, self.session.call_tool, name, arguments)
            return result.content

    async def get_resources(self) -> List[Any]:
        import anyio
        try:
            await self._ensure_connected()
            result = await anyio.to_thread.run_sync(self._portal.call, self.session.list_resources)
            return result.resources
        except Exception:
            self.session = None
            await self._ensure_connected()
            result = await anyio.to_thread.run_sync(self._portal.call, self.session.list_resources)
            return result.resources

    async def read_resource(self, uri: str) -> str:
        import anyio
        try:
            await self._ensure_connected()
            result = await anyio.to_thread.run_sync(self._portal.call, self.session.read_resource, uri)
            return result.contents[0].text
        except Exception:
            self.session = None
            await self._ensure_connected()
            result = await anyio.to_thread.run_sync(self._portal.call, self.session.read_resource, uri)
            return result.contents[0].text

    async def get_prompts(self) -> List[Any]:
        import anyio
        try:
            await self._ensure_connected()
            result = await anyio.to_thread.run_sync(self._portal.call, self.session.list_prompts)
            return result.prompts
        except Exception:
            self.session = None
            await self._ensure_connected()
            result = await anyio.to_thread.run_sync(self._portal.call, self.session.list_prompts)
            return result.prompts

    async def get_prompt_content(self, name: str, arguments: dict = None) -> Any:
        import anyio
        try:
            await self._ensure_connected()
            result = await anyio.to_thread.run_sync(self._portal.call, self.session.get_prompt, name, arguments)
            return result.messages[0].content.text
        except Exception:
            try:
                self.session = None
                await self._ensure_connected()
                result = await anyio.to_thread.run_sync(self._portal.call, self.session.get_prompt, name, arguments)
                return result.messages[0].content.text
            except AttributeError:
                return str(result)

    async def close(self):
        if self._session_ctx:
            try:
                self._session_ctx.__exit__(None, None, None)
            except Exception:
                pass
            self._session_ctx = None
        if self._stdio_ctx:
            try:
                self._stdio_ctx.__exit__(None, None, None)
            except Exception:
                pass
            self._stdio_ctx = None
        if self._portal_ctx:
            try:
                self._portal_ctx.__exit__(None, None, None)
            except Exception:
                pass
            self._portal_ctx = None
            self._portal = None
        self.session = None

# Global instances for different servers
food_knowledge_client = None
weather_client = None
restaurant_client = None
prompt_client = None

def get_food_knowledge_client():
    global food_knowledge_client
    if food_knowledge_client is None:
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../mcp_servers/food_knowledge/server.py"))
        food_knowledge_client = MCPClient(script_path)
    return food_knowledge_client

def get_weather_client():
    global weather_client
    if weather_client is None:
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../mcp_servers/weather/server.py"))
        weather_client = MCPClient(script_path)
    return weather_client

def get_restaurant_client():
    global restaurant_client
    if restaurant_client is None:
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../mcp_servers/restaurants/server.py"))
        restaurant_client = MCPClient(script_path)
    return restaurant_client

def get_prompt_client():
    global prompt_client
    if prompt_client is None:
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../mcp_servers/prompts/server.py"))
        prompt_client = MCPClient(script_path)
    return prompt_client

async def init_all_clients():
    await get_food_knowledge_client().connect()
    await get_weather_client().connect()
    await get_restaurant_client().connect()
    await get_prompt_client().connect()

async def close_all_clients():
    if food_knowledge_client: await food_knowledge_client.close()
    if weather_client: await weather_client.close()
    if restaurant_client: await restaurant_client.close()
    if prompt_client: await prompt_client.close()
