from __future__ import annotations

import datetime
from typing import Any, Callable, Literal

from gradio.components.base import Component


class Calendar(Component):
    """
    A calendar component that allows users to select a date.
    
    Preprocessing: The date passed to the python function will be a string formatted as YYYY-MM-DD or a datetime.datetime object
    depending on the value of the type parameter.

    Postprocessing: The value returned from the function can be a string or a datetime.datetime object. 
    
    Parameters:
        value: The default date value, formatted as YYYY-MM-DD. Can be either a string or datetime.datetime object.
        type: The type of the value to pass to the python function. Either "string" or "datetime".
        label: The label for the component.
        info: Extra text to render below the component.
        show_label: Whether to show the label for the component.
        container: Whether to show the component in a container.
        scale: The relative size of the component compared to other components in the same row.
        min_width: The minimum width of the component.
        interactive: Whether to allow the user to interact with the component.
        visible: Whether to show the component.
        elem_id: The id of the component. Useful for custom js or css.
        elem_classes: The classes of the component. Useful for custom js or css.
        render: Whether to render the component in the parent Blocks scope.
        load_fn: A function to run when the component is first loaded onto the page to set the intial value.
        every: Whether load_fn should be run on a fixed time interval.
    """

    EVENTS = ["change", "input", "submit"]

    def __init__(self, value: str | datetime.datetime = None, *,
                 type: Literal["string", "datetime"] = "datetime",
                 label: str | None = None, info: str | None = None,
                 show_label: bool | None = None, container: bool = True, scale: int | None = None,
                 min_width: int | None = None, interactive: bool | None = None, visible: bool = True,
                 elem_id: str | None = None, elem_classes: list[str] | str | None = None,
                 render: bool = True,
                 load_fn: Callable[..., Any] | None = None,
                 every: float | None = None):
        self._format_str = "%Y-%m-%d"
        self.type = type
        super().__init__(value, label=label, info=info, show_label=show_label, container=container, scale=scale,
                         min_width=min_width, interactive=interactive, visible=visible, elem_id=elem_id,
                         elem_classes=elem_classes, render=render, load_fn=load_fn, every=every)

    def preprocess(self, payload: str | None) -> str | datetime.datetime | None:
        if payload is None:
            return None
        if self.type == "string":
            return payload
        else:
            return datetime.datetime.strptime(payload, self._format_str)

    def postprocess(self, value: str | datetime.datetime | None) -> str | None:
        if not value:
            return None
        if isinstance(value, str):
            return datetime.datetime.strptime(value, self._format_str).strftime(self._format_str)
        elif isinstance(value, datetime.datetime):
            return datetime.datetime.strftime(value, self._format_str)
        else:
            raise ValueError(f"Unexpected value type {type(value)} for Calender (value: {value})")

    def example_inputs(self):
        return "2023-01-01"

    def api_info(self):
        return {"type": "string", "description": f"Date string formatted as YYYY-MM-DD."}
