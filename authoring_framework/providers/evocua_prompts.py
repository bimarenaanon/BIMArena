"""EvoCUA's own S2 prompt and tool definition, VERBATIM.

Copied from meituan/EvoCUA `mm_agents/evocua/prompts.py` (Apache-2.0) — the system prompt,
the `computer_use` function description and the tool schema the model was fine-tuned on.
Kept byte-for-byte so the benchmark drives the model exactly as its own harness does; the
S1 (trajectory-generation) prompt is not needed and was left out. Do not edit the wording:
a CUA fine-tune is sensitive to its training-time prompt, and any drift here would be
measured as model behaviour. The adapter that uses these is `providers/evocua.py`.
"""
import json  # noqa: F401  (kept for parity with the upstream module)


# S2 Prompts
S2_ACTION_DESCRIPTION = """
* `key`: Performs key down presses on the arguments passed in order, then performs key releases in reverse order.
* `key_down`: Press and HOLD the specified key(s) down in order (no release). Use this for stateful holds like holding Shift while clicking.
* `key_up`: Release the specified key(s) in reverse order.
* `type`: Type a string of text on the keyboard.
* `mouse_move`: Move the cursor to a specified (x, y) pixel coordinate on the screen.
* `left_click`: Click the left mouse button at a specified (x, y) pixel coordinate on the screen.
* `left_click_drag`: Click and drag the cursor to a specified (x, y) pixel coordinate on the screen.
* `right_click`: Click the right mouse button at a specified (x, y) pixel coordinate on the screen.
* `middle_click`: Click the middle mouse button at a specified (x, y) pixel coordinate on the screen.
* `double_click`: Double-click the left mouse button at a specified (x, y) pixel coordinate on the screen.
* `triple_click`: Triple-click the left mouse button at a specified (x, y) pixel coordinate on the screen.
* `scroll`: Performs a scroll of the mouse scroll wheel.
* `hscroll`: Performs a horizontal scroll (mapped to regular scroll).
* `wait`: Wait specified seconds for the change to happen.
* `terminate`: Terminate the current task and report its completion status.
* `answer`: Answer a question.
"""

S2_DESCRIPTION_PROMPT_TEMPLATE = """Use a mouse and keyboard to interact with a computer, and take screenshots.
* This is an interface to a desktop GUI. You must click on desktop icons to start applications.
* Some applications may take time to start or process actions, so you may need to wait and take successive screenshots to see the results of your actions. E.g. if you click on Firefox and a window doesn't open, try wait and taking another screenshot.
{resolution_info}
* Whenever you intend to move the cursor to click on an element like an icon, you should consult a screenshot to determine the coordinates of the element before moving the cursor.
* If you tried clicking on a program or link but it failed to load even after waiting, try adjusting your cursor position so that the tip of the cursor visually falls on the element that you want to click.
* Make sure to click any buttons, links, icons, etc with the cursor tip in the center of the element. Don't click boxes on their edges unless asked."""

S2_SYSTEM_PROMPT = """# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
{tools_xml}
</tools>

For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:
<tool_call>
{{"name": <function-name>, "arguments": <args-json-object>}}
</tool_call>

# Response format

Response format for every step:
1) Action: a short imperative describing what to do in the UI.
2) A single <tool_call>...</tool_call> block containing only the JSON: {{"name": <function-name>, "arguments": <args-json-object>}}.

Rules:
- Output exactly in the order: Action, <tool_call>.
- Be brief: one sentence for Action.
- Do not output anything else outside those parts.
- If finishing, use action=terminate in the tool call."""


def build_s2_tools_def(description_prompt):
    return {
        "type": "function", 
        "function": {
            "name_for_human": "computer_use", 
            "name": "computer_use", 
            "description": description_prompt,
            "parameters": {
                "properties": {
                    "action": {
                        "description": S2_ACTION_DESCRIPTION,
                        "enum": ["key", "type", "mouse_move", "left_click", "left_click_drag", 
                                 "right_click", "middle_click", "double_click", "triple_click", "scroll", 
                                 "wait", "terminate", "key_down", "key_up"], 
                        "type": "string"
                    },
                    "keys": {"description": "Required only by `action=key`.", "type": "array"}, 
                    "text": {"description": "Required only by `action=type`.", "type": "string"}, 
                    "coordinate": {"description": "The x,y coordinates for mouse actions.", "type": "array"}, 
                    "pixels": {"description": "The amount of scrolling.", "type": "number"}, 
                    "time": {"description": "The seconds to wait.", "type": "number"}, 
                    "status": {
                        "description": "The status of the task.", 
                        "type": "string", 
                        "enum": ["success", "failure"]
                    }
                }, 
                "required": ["action"], 
                "type": "object"
            }, 
            "args_format": "Format the arguments as a JSON object."
        }
    }

