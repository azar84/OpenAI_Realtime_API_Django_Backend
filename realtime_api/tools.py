"""
OpenAI Realtime API Tools
=========================

This module contains all the function tools that can be called by the AI agents
during conversations. Each tool is a separate function that can be registered
and called dynamically.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# WEATHER TOOLS
# =============================================================================

async def get_weather(location: str) -> Dict[str, Any]:
    """
    Get current weather information for a location.
    
    Args:
        location (str): The city and state, e.g. "San Francisco, CA"
        
    Returns:
        Dict containing weather information
    """
    logger.info(f"🌤️ Getting weather for: {location}")
    
    # Mock weather data - replace with real API call
    weather_data = {
        "location": location,
        "temperature": "72°F",
        "condition": "Sunny",
        "humidity": "45%",
        "wind_speed": "8 mph",
        "description": f"It's a beautiful sunny day in {location} with comfortable temperatures."
    }
    
    logger.info(f"🌤️ Weather data: {weather_data}")
    return weather_data


async def get_weather_forecast(location: str, days: int = 3) -> Dict[str, Any]:
    """
    Get weather forecast for multiple days.
    
    Args:
        location (str): The city and state
        days (int): Number of days to forecast (1-7)
        
    Returns:
        Dict containing forecast information
    """
    logger.info(f"🌤️ Getting {days}-day forecast for: {location}")
    
    # Mock forecast data
    forecast = {
        "location": location,
        "forecast_days": days,
        "forecast": [
            {"day": "Today", "high": "75°F", "low": "58°F", "condition": "Sunny"},
            {"day": "Tomorrow", "high": "73°F", "low": "60°F", "condition": "Partly Cloudy"},
            {"day": "Day 3", "high": "71°F", "low": "55°F", "condition": "Light Rain"}
        ][:days]
    }
    
    return forecast


# =============================================================================
# TIME & DATE TOOLS
# =============================================================================

async def get_current_time(timezone: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the current time and date.
    
    Args:
        timezone (str, optional): Timezone name (e.g., "America/New_York")
        
    Returns:
        Dict containing current time information
    """
    logger.info(f"🕐 Getting current time for timezone: {timezone or 'UTC'}")
    
    now = datetime.now()
    
    time_data = {
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%A, %B %d, %Y"),
        "time": now.strftime("%I:%M %p"),
        "timezone": timezone or "UTC",
        "unix_timestamp": int(now.timestamp()),
        "day_of_week": now.strftime("%A"),
        "month": now.strftime("%B")
    }
    
    logger.info(f"🕐 Time data: {time_data}")
    return time_data


async def get_timezone_info(timezone: str) -> Dict[str, Any]:
    """
    Get information about a specific timezone.
    
    Args:
        timezone (str): Timezone name
        
    Returns:
        Dict containing timezone information
    """
    # Mock timezone data - replace with real timezone library
    return {
        "timezone": timezone,
        "offset": "-08:00",
        "description": f"Information about {timezone} timezone"
    }


# =============================================================================
# UTILITY TOOLS
# =============================================================================

async def calculate_math(expression: str) -> Dict[str, Any]:
    """
    Perform basic math calculations.
    
    Args:
        expression (str): Mathematical expression to evaluate
        
    Returns:
        Dict containing calculation result
    """
    logger.info(f"🔢 Calculating: {expression}")
    
    try:
        # Simple and safe evaluation for basic math
        # Only allow basic operators and numbers
        allowed_chars = set('0123456789+-*/.() ')
        if not all(c in allowed_chars for c in expression):
            raise ValueError("Invalid characters in expression")
        
        result = eval(expression)
        
        return {
            "expression": expression,
            "result": result,
            "formatted_result": f"{expression} = {result}"
        }
    except Exception as e:
        logger.error(f"🔢 Math calculation error: {e}")
        return {
            "expression": expression,
            "error": f"Could not calculate: {str(e)}",
            "result": None
        }


# =============================================================================
# TOOL REGISTRY
# =============================================================================

# Registry of all available tools with their metadata
TOOL_REGISTRY = {
    "get_weather": {
        "function": get_weather,
        "description": "Get current weather for a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state, e.g. San Francisco, CA"
                }
            },
            "required": ["location"]
        }
    },
    "get_weather_forecast": {
        "function": get_weather_forecast,
        "description": "Get weather forecast for multiple days",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days to forecast (1-7)",
                    "minimum": 1,
                    "maximum": 7
                }
            },
            "required": ["location"]
        }
    },
    "get_time": {
        "function": get_current_time,
        "description": "Get current time",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "get_current_time": {
        "function": get_current_time,
        "description": "Get current time and date",
        "parameters": {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "Timezone name (optional)"
                }
            },
            "required": []
        }
    },
    "calculate_math": {
        "function": calculate_math,
        "description": "Perform basic math calculations",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate (e.g., '2 + 2', '10 * 5')"
                }
            },
            "required": ["expression"]
        }
    }
}


# =============================================================================
# TOOL EXECUTION
# =============================================================================

async def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a tool by name with given arguments.
    
    Args:
        tool_name (str): Name of the tool to execute
        arguments (dict): Arguments to pass to the tool
        
    Returns:
        Dict containing the tool execution result
    """
    logger.info(f"🔧 Executing tool: {tool_name} with args: {arguments}")
    
    if tool_name not in TOOL_REGISTRY:
        error_msg = f"Unknown tool: {tool_name}"
        logger.error(f"🔧 {error_msg}")
        return {"error": error_msg}
    
    try:
        tool_function = TOOL_REGISTRY[tool_name]["function"]
        result = await tool_function(**arguments)
        logger.info(f"🔧 Tool {tool_name} executed successfully")
        return result
    except Exception as e:
        error_msg = f"Error executing tool {tool_name}: {str(e)}"
        logger.error(f"🔧 {error_msg}")
        return {"error": error_msg}


def get_tools_for_openai() -> list:
    """
    Get the tools formatted for OpenAI function calling.
    
    Returns:
        List of tool definitions for OpenAI API
    """
    tools = []
    for tool_name, tool_info in TOOL_REGISTRY.items():
        tools.append({
            "type": "function",
            "name": tool_name,
            "description": tool_info["description"],
            "parameters": tool_info["parameters"]
        })
    return tools


def get_available_tools() -> Dict[str, str]:
    """
    Get a summary of all available tools.
    
    Returns:
        Dict mapping tool names to descriptions
    """
    return {name: info["description"] for name, info in TOOL_REGISTRY.items()}
