from pathlib import Path
from shared.prompts import PromptLoader

prompt_loader = PromptLoader(Path(__file__).parent)

__all__ = ["prompt_loader"]
