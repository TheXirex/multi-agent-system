from pathlib import Path
from typing import Any
from jinja2 import Environment, FileSystemLoader, select_autoescape


class PromptLoader:
    """
    Loads and renders Jinja2 prompt templates from a specified directory.
    """

    def __init__(self, template_dir: Path | str) -> None:
        self.template_dir = Path(template_dir)
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(disabled_extensions=("j2", "jinja2", "txt", "md")),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, template_name: str, **kwargs: Any) -> str:
        """
        Renders a Jinja2 template by name with supplied parameters.

        Args:
            template_name (str): Name of the template file (with or without .j2 extension).
            **kwargs: Context variables passed to template.

        Returns:
            str: Rendered prompt string.
        """
        filename = template_name if template_name.endswith(".j2") else f"{template_name}.j2"
        template = self.env.get_template(filename)
        return template.render(**kwargs).strip()
