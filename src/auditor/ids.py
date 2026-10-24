from auditor.models import SECTION_ID


def slug(id: str) -> str:
    if not SECTION_ID.match(id):
        raise ValueError(f"not a canonical section id: {id!r}")
    return id.replace(":", "__").replace(".", "_")
