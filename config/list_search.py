from functools import reduce
from operator import or_

from django.db.models import Q


def filter_rows(request, rows, fields, *, split_terms=False):
    """Filter a listing using its declared search columns and expose them to the search bar."""
    query = request.GET.get("q", "").strip()[:200]
    selected = request.GET.get("field", "")
    active = fields.get(selected)
    request.list_search = {
        "query": query,
        "fields": [(key, label) for key, (label, *_) in fields.items()],
        "selected": selected if active else "",
        "placeholder": active[0] if active else "Tous les champs",
    }
    lookups = (active,) if active else fields.values()
    terms = query.split() if split_terms else ([query] if query else [])
    for term in terms:
        conditions = (
            lookup(term) if callable(lookup) else Q(**{lookup: term})
            for _, *columns in lookups for lookup in columns
        )
        rows = rows.filter(reduce(or_, conditions))
    return rows, query
