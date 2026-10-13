from typing import Mapping


def overall_coverage(modules: Mapping[str, str]) -> str:
    return "complete" if modules and all(value == "complete" for value in modules.values()) else "partial"
