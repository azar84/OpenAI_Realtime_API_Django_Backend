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
    # Mock weather data - replace with real API call
    weather_data = {
        "location": location,
        "temperature": "72°F",
        "condition": "Sunny",
        "humidity": "45%",
        "wind_speed": "8 mph",
        "description": f"It's a beautiful sunny day in {location} with comfortable temperatures."
    }
    
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
    logger.info(f"🧮 MATH CALCULATION: Starting calculation for: {expression}")
    
    try:
        # Simple and safe evaluation for basic math
        # Only allow basic operators and numbers
        allowed_chars = set('0123456789+-*/.() ')
        if not all(c in allowed_chars for c in expression):
            invalid_chars = [c for c in expression if c not in allowed_chars]
            error_msg = f"Invalid characters in expression: {invalid_chars}"
            logger.error(f"🧮 MATH CALCULATION: {error_msg}")
            logger.error(f"🧮 MATH CALCULATION: Expression: {expression}")
            logger.error(f"🧮 MATH CALCULATION: Allowed chars: {sorted(allowed_chars)}")
            raise ValueError(error_msg)
        
        logger.info(f"🧮 MATH CALCULATION: Expression validated, evaluating...")
        result = eval(expression)
        
        logger.info(f"🧮 MATH CALCULATION: ===== CALCULATION SUCCESS =====")
        logger.info(f"🧮 MATH CALCULATION: Expression: {expression}")
        logger.info(f"🧮 MATH CALCULATION: Result: {result}")
        logger.info(f"🧮 MATH CALCULATION: Result Type: {type(result).__name__}")
        
        return {
            "expression": expression,
            "result": result,
            "formatted_result": f"{expression} = {result}",
            "result_type": type(result).__name__
        }
    except ValueError as e:
        error_msg = f"Invalid expression: {str(e)}"
        logger.error(f"🧮 MATH CALCULATION: ===== VALUE ERROR =====")
        logger.error(f"🧮 MATH CALCULATION: {error_msg}")
        logger.error(f"🧮 MATH CALCULATION: Expression: {expression}")
        return {
            "expression": expression,
            "error": error_msg,
            "error_type": "ValueError",
            "result": None
        }
    except ZeroDivisionError as e:
        error_msg = f"Division by zero: {str(e)}"
        logger.error(f"🧮 MATH CALCULATION: ===== DIVISION BY ZERO =====")
        logger.error(f"🧮 MATH CALCULATION: {error_msg}")
        logger.error(f"🧮 MATH CALCULATION: Expression: {expression}")
        return {
            "expression": expression,
            "error": error_msg,
            "error_type": "ZeroDivisionError",
            "result": None
        }
    except Exception as e:
        error_msg = f"Calculation error: {str(e)}"
        logger.error(f"🧮 MATH CALCULATION: ===== UNEXPECTED ERROR =====")
        logger.error(f"🧮 MATH CALCULATION: {error_msg}")
        logger.error(f"🧮 MATH CALCULATION: Expression: {expression}")
        logger.error(f"🧮 MATH CALCULATION: Error Type: {type(e).__name__}")
        return {
            "expression": expression,
            "error": error_msg,
            "error_type": type(e).__name__,
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
    # Enhanced debug logging
    logger.info(f"🔧 TOOL EXECUTION: ===== TOOL EXECUTION START =====")
    logger.info(f"🔧 TOOL EXECUTION: Tool Name: {tool_name}")
    logger.info(f"🔧 TOOL EXECUTION: Arguments: {json.dumps(arguments, indent=2)}")
    logger.info(f"🔧 TOOL EXECUTION: Timestamp: {datetime.now().isoformat()}")
    logger.info(f"🔧 TOOL EXECUTION: Available Tools: {list(TOOL_REGISTRY.keys())}")
    
    if tool_name not in TOOL_REGISTRY:
        error_msg = f"Unknown tool: {tool_name}"
        logger.error(f"🔧 TOOL EXECUTION: ===== TOOL NOT FOUND =====")
        logger.error(f"🔧 TOOL EXECUTION: {error_msg}")
        logger.error(f"🔧 TOOL EXECUTION: Available tools: {list(TOOL_REGISTRY.keys())}")
        return {
            "error": error_msg,
            "available_tools": list(TOOL_REGISTRY.keys()),
            "tool_name": tool_name,
            "arguments": arguments
        }
    
    try:
        # Get tool function and metadata
        tool_info = TOOL_REGISTRY[tool_name]
        tool_function = tool_info["function"]
        tool_description = tool_info["description"]
        
        logger.info(f"🔧 TOOL EXECUTION: Tool Found: {tool_name}")
        logger.info(f"🔧 TOOL EXECUTION: Description: {tool_description}")
        logger.info(f"🔧 TOOL EXECUTION: Function: {tool_function.__name__}")
        
        # Validate arguments against schema
        required_params = tool_info["parameters"].get("required", [])
        logger.info(f"🔧 TOOL EXECUTION: Required Parameters: {required_params}")
        logger.info(f"🔧 TOOL EXECUTION: Provided Arguments: {list(arguments.keys())}")
        
        # Check for missing required parameters
        missing_params = [param for param in required_params if param not in arguments]
        if missing_params:
            error_msg = f"Missing required parameters: {missing_params}"
            logger.error(f"🔧 TOOL EXECUTION: ===== MISSING PARAMETERS =====")
            logger.error(f"🔧 TOOL EXECUTION: {error_msg}")
            logger.error(f"🔧 TOOL EXECUTION: Required: {required_params}")
            logger.error(f"🔧 TOOL EXECUTION: Provided: {list(arguments.keys())}")
            return {
                "error": error_msg,
                "missing_parameters": missing_params,
                "required_parameters": required_params,
                "provided_arguments": list(arguments.keys()),
                "tool_name": tool_name
            }
        
        # Execute the tool
        logger.info(f"🔧 TOOL EXECUTION: Starting execution...")
        result = await tool_function(**arguments)
        
        # Enhanced success logging
        logger.info(f"🔧 TOOL EXECUTION: ===== TOOL EXECUTION SUCCESS =====")
        logger.info(f"🔧 TOOL EXECUTION: Tool: {tool_name}")
        logger.info(f"🔧 TOOL EXECUTION: Result Type: {type(result).__name__}")
        if isinstance(result, dict):
            logger.info(f"🔧 TOOL EXECUTION: Result Keys: {list(result.keys())}")
            if 'error' in result:
                logger.warning(f"🔧 TOOL EXECUTION: Tool returned error in result: {result['error']}")
            else:
                logger.info(f"🔧 TOOL EXECUTION: Result: {json.dumps(result, indent=2)}")
        else:
            logger.info(f"🔧 TOOL EXECUTION: Result: {str(result)}")
        
        return result
        
    except TypeError as e:
        error_msg = f"Type error executing tool {tool_name}: {str(e)}"
        logger.error(f"🔧 TOOL EXECUTION: ===== TYPE ERROR =====")
        logger.error(f"🔧 TOOL EXECUTION: {error_msg}")
        logger.error(f"🔧 TOOL EXECUTION: Arguments: {arguments}")
        logger.error(f"🔧 TOOL EXECUTION: Tool function signature: {tool_function.__name__}")
        return {
            "error": error_msg,
            "error_type": "TypeError",
            "tool_name": tool_name,
            "arguments": arguments,
            "function_name": tool_function.__name__
        }
    except ValueError as e:
        error_msg = f"Value error executing tool {tool_name}: {str(e)}"
        logger.error(f"🔧 TOOL EXECUTION: ===== VALUE ERROR =====")
        logger.error(f"🔧 TOOL EXECUTION: {error_msg}")
        logger.error(f"🔧 TOOL EXECUTION: Arguments: {arguments}")
        return {
            "error": error_msg,
            "error_type": "ValueError",
            "tool_name": tool_name,
            "arguments": arguments
        }
    except Exception as e:
        error_msg = f"Unexpected error executing tool {tool_name}: {str(e)}"
        logger.error(f"🔧 TOOL EXECUTION: ===== UNEXPECTED ERROR =====")
        logger.error(f"🔧 TOOL EXECUTION: {error_msg}")
        logger.error(f"🔧 TOOL EXECUTION: Error Type: {type(e).__name__}")
        logger.error(f"🔧 TOOL EXECUTION: Arguments: {arguments}")
        logger.error(f"🔧 TOOL EXECUTION: Tool: {tool_name}")
        logger.error(f"🔧 TOOL EXECUTION: Timestamp: {datetime.now().isoformat()}")
        return {
            "error": error_msg,
            "error_type": type(e).__name__,
            "tool_name": tool_name,
            "arguments": arguments,
            "exception_details": str(e)
        }


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
